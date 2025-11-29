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
    POST /api/tasks/analyze/ - Fetch tasks from DB and analyze them
    """
    try:
        strategy = request.data.get('strategy', 'smart_balance')
        
        # Fetch all tasks from DB
        tasks_qs = Task.objects.filter(is_done=False)
        
        if not tasks_qs.exists():
            return Response({
                'success': True,
                'tasks': [],
                'total_tasks': 0,
                'strategy_used': strategy,
                'timestamp': datetime.now().isoformat()
            }, status=status.HTTP_200_OK)
        
        # Convert to list for scorer
        tasks_list = []
        for task in tasks_qs:
            tasks_list.append({
                'id': task.id,
                'title': task.title,
                'importance': task.importance,
                'estimated_hours': task.effort,
                'due_date': task.deadline.isoformat() if task.deadline else None,
                'dependencies': task.dependencies or []
            })
        
        # Analyze
        scorer = TaskScorer(strategy=strategy)
        circular_deps = scorer.detect_circular_dependencies(tasks_list)
        scored_tasks = scorer.analyze_tasks(tasks_list)
        
        # Update scores and calculated urgency in DB
        for scored_task in scored_tasks:
            task_id = scored_task['task']['id']
            # Calculate urgency from deadline
            deadline = scored_task['task'].get('due_date')
            urgency_score = scorer.calculate_urgency_score(deadline)
            # Convert to 1-10 scale for storage
            urgency_rating = int((urgency_score / 40) * 10)
            
            Task.objects.filter(id=task_id).update(
                priority_score=scored_task['score'],
                score_breakdown=scored_task.get('breakdown', {}),
                urgency=urgency_rating
            )
        
        response_data = {
            'success': True,
            'strategy_used': strategy,
            'total_tasks': len(scored_tasks),
            'tasks': scored_tasks,
            'timestamp': datetime.now().isoformat()
        }
        
        if circular_deps:
            response_data['circular_dependencies'] = [list(cycle) for cycle in circular_deps]
            response_data['warning'] = 'Circular dependencies detected'
        
        return Response(response_data, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def add_task(request):
    """
    POST /api/tasks/add/ - Add a single task to DB
    """
    try:
        data = request.data
        
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
        
        task = Task.objects.create(
            id=data['id'],
            title=data['title'],
            description=data.get('description', ''),
            importance=data.get('importance', 5),
            effort=data.get('effort', 5),
            deadline=data.get('deadline'),
            dependencies=data.get('dependencies', [])
        )
        
        return Response({
            'success': True,
            'message': f'Task "{task.title}" added',
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
    POST /api/tasks/add-bulk/ - Add multiple tasks to DB
    """
    try:
        tasks = request.data.get('tasks', [])
        
        if not tasks or not isinstance(tasks, list):
            return Response({
                'success': False,
                'error': 'Tasks array is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        created_count = 0
        for task_data in tasks:
            if task_data.get('title') and task_data.get('id'):
                Task.objects.create(
                    id=task_data['id'],
                    title=task_data['title'],
                    description=task_data.get('description', ''),
                    importance=task_data.get('importance', 5),
                    urgency=task_data.get('urgency', 5),
                    effort=task_data.get('effort', 5),
                    deadline=task_data.get('deadline'),
                    dependencies=task_data.get('dependencies', [])
                )
                created_count += 1
        
        return Response({
            'success': True,
            'message': f'{created_count} tasks added',
            'count': created_count
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
def mark_done(request, task_id):
    """
    DELETE /api/tasks/<id>/done/ - Mark task as done (delete from DB) and re-analyze
    """
    try:
        task = Task.objects.get(id=task_id, is_done=False)
        task_title = task.title
        task.delete()
        
        # Re-analyze remaining tasks
        strategy = request.data.get('strategy', 'smart_balance') if request.data else 'smart_balance'
        remaining_tasks_qs = Task.objects.filter(is_done=False)
        
        if remaining_tasks_qs.exists():
            tasks_list = []
            for t in remaining_tasks_qs:
                tasks_list.append({
                    'id': t.id,
                    'title': t.title,
                    'description': t.description,
                    'importance': t.importance,
                    'urgency': t.urgency,
                    'effort': t.effort,
                    'deadline': t.deadline.isoformat() if t.deadline else None,
                    'dependencies': t.dependencies
                })
            
            scorer = TaskScorer(strategy=strategy)
            scored_tasks = scorer.analyze_tasks(tasks_list)
            
            # Update scores
            for scored_task in scored_tasks:
                Task.objects.filter(id=scored_task['task']['id']).update(
                    priority_score=scored_task['score'],
                    score_breakdown=scored_task.get('breakdown', {})
                )
            
            return Response({
                'success': True,
                'message': f'Task "{task_title}" completed',
                'remaining_tasks': scored_tasks
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': True,
                'message': f'Task "{task_title}" completed',
                'remaining_tasks': []
            }, status=status.HTTP_200_OK)
    
    except Task.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Task not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
def clear_all_tasks(request):
    """
    DELETE /api/tasks/clear/ - Delete all tasks from DB
    """
    try:
        count = Task.objects.all().count()
        Task.objects.all().delete()
        
        return Response({
            'success': True,
            'message': f'Deleted {count} tasks from database'
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
    
    Return the top N tasks from database that user should work on today.
    
    Response:
    {
        "success": true,
        "suggestions": [...]
    }
    """
    try:
        count = int(request.GET.get('count', 3))
        strategy = request.GET.get('strategy', 'smart_balance')
        
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
                'timestamp': datetime.now().isoformat()
            }, status=status.HTTP_200_OK)
        
        # Convert to list
        tasks_list = []
        for task in tasks_qs:
            tasks_list.append({
                'id': task.id,
                'title': task.title,
                'description': task.description,
                'importance': task.importance,
                'urgency': task.urgency,
                'effort': task.effort,
                'deadline': task.deadline.isoformat() if task.deadline else None,
                'dependencies': task.dependencies
            })
        
        # Get suggestions
        scorer = TaskScorer(strategy=strategy)
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
    
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def health_check(request):
    """Simple health check endpoint."""
    return Response(
        {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat()
        },
        status=status.HTTP_200_OK
    )


