# tasks/views.py
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .scoring import TaskScorer
from .models import Task
from datetime import datetime
from django.utils import timezone


@api_view(['POST'])
def analyze_tasks(request):
    """
    POST /api/tasks/analyze/
    
    Fetch tasks from DB and analyze them with priority scoring.
    Accepts optional 'strategy' parameter.
    """
    try:
        strategy = request.data.get('strategy', 'smart_balance')
        
        # Fetch all incomplete tasks from DB
        tasks_qs = Task.objects.filter(is_done=False)
        
        if not tasks_qs.exists():
            return Response({
                'success': True,
                'tasks': [],
                'total_tasks': 0,
                'strategy_used': strategy,
                'timestamp': datetime.now().isoformat()
            }, status=status.HTTP_200_OK)
        
        # Convert DB tasks to scorer format
        tasks_list = []
        for task in tasks_qs:
            tasks_list.append({
                'id': str(task.id),  # Ensure string ID
                'title': task.title,
                'description': task.description,
                'importance': task.importance,
                'estimated_hours': task.effort,  # Map effort -> estimated_hours
                'due_date': task.due_date.isoformat() if task.due_date else None,  # Map due_date -> due_date
                'dependencies': task.dependencies if task.dependencies else []
            })
        
        # Initialize scorer with holiday support for India
        scorer = TaskScorer(strategy=strategy, country='IN', consider_holidays=True)
        
        # Detect circular dependencies
        circular_deps = scorer.detect_circular_dependencies(tasks_list)
        
        # Analyze and score all tasks
        scored_tasks = scorer.analyze_tasks(tasks_list)
        
        # Update scores in database
        for scored_task in scored_tasks:
            task_id = scored_task['task']['id']
            Task.objects.filter(id=task_id).update(
                priority_score=scored_task['score'],
                score_breakdown=scored_task.get('breakdown', {})
            )
        
        # Prepare response
        response_data = {
            'success': True,
            'strategy_used': strategy,
            'total_tasks': len(scored_tasks),
            'tasks': scored_tasks,
            'timestamp': datetime.now().isoformat()
        }
        
        # Add warning if circular dependencies detected
        if circular_deps:
            response_data['circular_dependencies'] = [list(cycle) for cycle in circular_deps]
            response_data['warning'] = 'Circular dependencies detected'
        
        return Response(response_data, status=status.HTTP_200_OK)
    
    except Exception as e:
        import traceback
        return Response({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def add_task(request):
    """
    POST /api/tasks/add/
    
    Add a single task to database.
    
    Required fields: id, title
    Optional: description, importance, effort, due_date, dependencies
    """
    try:
        data = request.data
        
        # Validation
        if not data.get('title'):
            return Response({
                'success': False,
                'error': 'Title is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not data.get('id'):
            return Response({
                'success': False,
                'error': 'ID is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if task with this ID already exists
        if Task.objects.filter(id=data['id']).exists():
            return Response({
                'success': False,
                'error': f'Task with ID "{data["id"]}" already exists'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create task
        task = Task.objects.create(
            id=data['id'],
            title=data['title'],
            description=data.get('description', ''),
            importance=data.get('importance', 5),
            effort=data.get('effort', data.get('estimated_hours')),  # Support both field names
            due_date=data.get('due_date', data.get('due_date')),  # Support both field names
            dependencies=data.get('dependencies', [])
        )
        
        return Response({
            'success': True,
            'message': f'Task "{task.title}" added successfully',
            'task_id': task.id
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def add_bulk_tasks(request):
    """
    POST /api/tasks/add-bulk/
    
    Add multiple tasks to database at once.
    
    Request body: { "tasks": [...] }
    """
    try:
        tasks = request.data.get('tasks', [])
        
        if not tasks or not isinstance(tasks, list):
            return Response({
                'success': False,
                'error': 'Tasks array is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        created_count = 0
        skipped_count = 0
        errors = []
        
        for idx, task_data in enumerate(tasks):
            try:
                # Validate required fields
                if not task_data.get('title'):
                    errors.append(f"Task {idx}: Missing title")
                    skipped_count += 1
                    continue
                
                if not task_data.get('id'):
                    errors.append(f"Task {idx}: Missing id")
                    skipped_count += 1
                    continue
                
                # Skip if already exists
                if Task.objects.filter(id=task_data['id']).exists():
                    errors.append(f"Task {idx}: ID '{task_data['id']}' already exists")
                    skipped_count += 1
                    continue
                
                # Create task
                Task.objects.create(
                    id=task_data['id'],
                    title=task_data['title'],
                    description=task_data.get('description', ''),
                    importance=task_data.get('importance', 5),
                    effort=task_data.get('effort', task_data.get('estimated_hours')),
                    due_date=task_data.get('due_date', task_data.get('due_date')),
                    dependencies=task_data.get('dependencies', [])
                )
                created_count += 1
                
            except Exception as e:
                errors.append(f"Task {idx}: {str(e)}")
                skipped_count += 1
        
        response = {
            'success': True,
            'message': f'{created_count} tasks added, {skipped_count} skipped',
            'created': created_count,
            'skipped': skipped_count
        }
        
        if errors:
            response['errors'] = errors
        
        return Response(response, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
def mark_done(request, task_id):
    """
    DELETE /api/tasks/<id>/done/
    
    Mark task as complete (delete from DB) and re-analyze remaining tasks.
    """
    try:
        # Find and delete the task
        task = Task.objects.get(id=task_id, is_done=False)
        task_title = task.title
        task.delete()
        
        # Get strategy from request
        strategy = request.data.get('strategy', 'smart_balance') if request.data else 'smart_balance'
        
        # Re-analyze remaining tasks
        remaining_tasks_qs = Task.objects.filter(is_done=False)
        
        if remaining_tasks_qs.exists():
            # Convert to scorer format
            tasks_list = []
            for t in remaining_tasks_qs:
                tasks_list.append({
                    'id': str(t.id),
                    'title': t.title,
                    'description': t.description,
                    'importance': t.importance,
                    'estimated_hours': t.effort,
                    'due_date': t.due_date.isoformat() if t.due_date else None,
                    'dependencies': t.dependencies if t.dependencies else []
                })
            
            # Re-score
            scorer = TaskScorer(strategy=strategy, country='IN')
            scored_tasks = scorer.analyze_tasks(tasks_list)
            
            # Update scores in DB
            for scored_task in scored_tasks:
                Task.objects.filter(id=scored_task['task']['id']).update(
                    priority_score=scored_task['score'],
                    score_breakdown=scored_task.get('breakdown', {})
                )
            
            return Response({
                'success': True,
                'message': f'Task "{task_title}" marked as complete',
                'remaining_tasks': scored_tasks
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': True,
                'message': f'Task "{task_title}" marked as complete. No tasks remaining.',
                'remaining_tasks': []
            }, status=status.HTTP_200_OK)
    
    except Task.DoesNotExist:
        return Response({
            'success': False,
            'error': f'Task with ID "{task_id}" not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
def clear_all_tasks(request):
    """
    DELETE /api/tasks/clear/
    
    Delete all tasks from database (useful for testing).
    """
    try:
        count = Task.objects.all().count()
        Task.objects.all().delete()
        
        return Response({
            'success': True,
            'message': f'Successfully deleted {count} task(s) from database'
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def suggest_tasks(request):
    """
    GET /api/tasks/suggest/?count=3&strategy=smart_balance
    
    Get top N task recommendations with explanations.
    """
    try:
        count = int(request.GET.get('count', 3))
        strategy = request.GET.get('strategy', 'smart_balance')
        
        # Validation
        if count < 1:
            return Response({
                'success': False,
                'error': 'Count must be a positive integer'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get incomplete tasks
        tasks_qs = Task.objects.filter(is_done=False)
        
        if not tasks_qs.exists():
            return Response({
                'success': True,
                'strategy_used': strategy,
                'suggestions': [],
                'message': 'No tasks available',
                'timestamp': datetime.now().isoformat()
            }, status=status.HTTP_200_OK)
        
        # Convert to scorer format
        tasks_list = []
        for task in tasks_qs:
            tasks_list.append({
                'id': str(task.id),
                'title': task.title,
                'description': task.description,
                'importance': task.importance,
                'estimated_hours': task.effort,
                'effort': task.effort,
                'due_date': task.due_date.isoformat() if task.due_date else None,
                'dependencies': task.dependencies if task.dependencies else []
            })
        
        # Get suggestions
        scorer = TaskScorer(strategy=strategy, country='IN')
        suggestions = scorer.suggest_top_tasks(tasks_list, count)
        circular_deps = scorer.detect_circular_dependencies(tasks_list)
        
        response_data = {
            'success': True,
            'strategy_used': strategy,
            'suggestions': suggestions,
            'timestamp': datetime.now().isoformat()
        }
        
        if circular_deps:
            response_data['circular_dependencies'] = [list(cycle) for cycle in circular_deps]
            response_data['warning'] = 'Circular dependencies detected'
        
        return Response(response_data, status=status.HTTP_200_OK)
    
    except ValueError:
        return Response({
            'success': False,
            'error': 'Invalid count parameter. Must be an integer.'
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def health_check(request):
    """
    GET /api/tasks/health/
    
    Simple health check endpoint to verify API is running.
    """
    task_count = Task.objects.filter(is_done=False).count()
    
    return Response({
        'status': 'healthy',
        'message': 'Task Analyzer API is running',
        'active_tasks': task_count,
        'timestamp': datetime.now().isoformat()
    }, status=status.HTTP_200_OK)