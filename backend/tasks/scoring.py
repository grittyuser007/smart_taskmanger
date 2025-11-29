# tasks/scoring.py
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
import math


class TaskScorer:
    """
    Intelligent task priority scoring system that balances multiple factors.
    
    Scoring Components:
    - Urgency Score (0-40): Based on days until due date
    - Importance Score (0-30): Direct mapping from user rating
    - Effort Score (0-15): Inverse relationship - quick wins get higher scores
    - Dependency Score (0-15): Tasks blocking others rank higher
    
    Total possible score: 100 points
    """
    
    def __init__(self, strategy='smart_balance'):
        """
        Initialize scorer with a specific strategy.
        
        Args:
            strategy: 'fastest_wins', 'high_impact', 'deadline_driven', or 'smart_balance'
        """
        self.strategy = strategy
        self.weights = self._get_strategy_weights()
    
    def _get_strategy_weights(self) -> Dict[str, float]:
        """Return weight multipliers based on selected strategy."""
        strategies = {
            'smart_balance': {
                'urgency': 1.0,
                'importance': 1.0,
                'effort': 1.0,
                'dependency': 1.0
            },
            'fastest_wins': {
                'urgency': 0.5,
                'importance': 0.7,
                'effort': 2.0,  # Double weight on quick tasks
                'dependency': 0.8
            },
            'high_impact': {
                'urgency': 0.6,
                'importance': 2.5,  # Heavily favor importance
                'effort': 0.3,
                'dependency': 0.8
            },
            'deadline_driven': {
                'urgency': 2.5,  # Heavily favor urgency
                'importance': 0.7,
                'effort': 0.5,
                'dependency': 1.0
            }
        }
        return strategies.get(self.strategy, strategies['smart_balance'])
    
    def calculate_urgency_score(self, due_date: Optional[str], current_date: datetime = None) -> float:
        """
        Calculate urgency score based on days until due date and urgency rating.
        
        Scoring logic:
        - If urgency rating provided (1-10): Use it scaled to 0-40
        - Overdue: 40 points (maximum urgency)
        - Due today: 38 points
        - Due in 1-3 days: 35-30 points (steep curve)
        - Due in 4-7 days: 25-20 points
        - Due in 1-2 weeks: 15-10 points
        - Due in 2+ weeks: 5-0 points
        
        Args:
            due_date: ISO format date string (YYYY-MM-DD)
            urgency_rating: User-provided urgency rating (1-10)
            current_date: Reference date (defaults to now)
        
        Returns:
            Urgency score (0-40)
        """
        
        if not due_date:
            return 10  # Default score for tasks without due dates
        
        if current_date is None:
            current_date = datetime.now()
        
        try:
            due = datetime.fromisoformat(due_date)
            days_until_due = (due.date() - current_date.date()).days
            
            # Overdue tasks get maximum urgency
            if days_until_due < 0:
                # Scale overdue tasks: more overdue = higher urgency
                overdue_days = abs(days_until_due)
                return min(40, 40 + (overdue_days * 0.5))  # Cap at 40 but signal severity
            
            # Due today
            if days_until_due == 0:
                return 38
            
            # Exponential decay for future tasks
            if days_until_due <= 3:
                return 35 - (days_until_due * 2)
            elif days_until_due <= 7:
                return 25 - ((days_until_due - 3) * 1.5)
            elif days_until_due <= 14:
                return 15 - ((days_until_due - 7))
            else:
                # Asymptotic approach to 0 for far future tasks
                return max(0, 5 - (days_until_due - 14) * 0.5)
        
        except (ValueError, TypeError):
            return 10  # Default for invalid dates
    
    def calculate_importance_score(self, importance: Optional[int]) -> float:
        """
        Map user importance rating (1-10) to score (0-30).
        
        Uses linear scaling: importance * 3
        
        Args:
            importance: User rating from 1-10
        
        Returns:
            Importance score (0-30)
        """
        if importance is None or not isinstance(importance, (int, float)):
            return 15  # Default mid-range score
        
        # Clamp to valid range
        importance = max(1, min(10, importance))
        return importance * 3
    
    def calculate_effort_score(self, estimated_hours: Optional[float]) -> float:
        """
        Calculate effort score favoring quick wins.
        
        Scoring logic (inverse relationship):
        - 0-1 hours: 15 points (quick wins)
        - 1-2 hours: 12 points
        - 2-4 hours: 9 points
        - 4-8 hours: 6 points
        - 8+ hours: 3 points
        
        Args:
            estimated_hours: Time to complete task
        
        Returns:
            Effort score (0-15)
        """
        if estimated_hours is None or estimated_hours <= 0:
            return 7.5  # Default mid-range score
        
        # Logarithmic decay - quick tasks get disproportionately higher scores
        if estimated_hours <= 1:
            return 15
        elif estimated_hours <= 2:
            return 12
        elif estimated_hours <= 4:
            return 9
        elif estimated_hours <= 8:
            return 6
        else:
            return max(3, 15 - math.log2(estimated_hours) * 2)
    
    def calculate_dependency_score(
        self, 
        task_id: str, 
        all_tasks: List[Dict],
        dependency_map: Dict[str, Set[str]]
    ) -> float:
        """
        Calculate score based on how many tasks depend on this one.
        
        Tasks that block many others should be prioritized.
        
        Scoring logic:
        - 0 dependents: 5 points (baseline)
        - 1 dependent: 8 points
        - 2 dependents: 11 points
        - 3+ dependents: 15 points
        
        Args:
            task_id: ID of current task
            all_tasks: List of all tasks
            dependency_map: Map of task_id -> set of tasks that depend on it
        
        Returns:
            Dependency score (0-15)
        """
        dependent_count = len(dependency_map.get(task_id, set()))
        
        if dependent_count == 0:
            return 5
        elif dependent_count == 1:
            return 8
        elif dependent_count == 2:
            return 11
        else:
            # Scale up for tasks blocking many others
            return min(15, 11 + (dependent_count - 2) * 1.5)
    
    def build_dependency_map(self, tasks: List[Dict]) -> Dict[str, Set[str]]:
        """
        Build reverse dependency map: task_id -> set of tasks depending on it.
        
        Also detects circular dependencies.
        
        Args:
            tasks: List of task dictionaries
        
        Returns:
            Dictionary mapping task IDs to their dependents
        """
        dependency_map = {}
        task_ids = {task.get('id', str(i)) for i, task in enumerate(tasks)}
        
        for i, task in enumerate(tasks):
            task_id = task.get('id', str(i))
            dependencies = task.get('dependencies', [])
            
            for dep_id in dependencies:
                # Validate dependency exists
                if dep_id in task_ids:
                    if dep_id not in dependency_map:
                        dependency_map[dep_id] = set()
                    dependency_map[dep_id].add(task_id)
        
        return dependency_map
    
    def detect_circular_dependencies(self, tasks: List[Dict]) -> List[tuple]:
        """
        Detect circular dependencies using depth-first search.
        
        Returns list of cycles found as tuples of task IDs.
        """
        task_map = {task.get('id', str(i)): task for i, task in enumerate(tasks)}
        visited = set()
        rec_stack = set()
        cycles = []
        
        def dfs(task_id: str, path: List[str]):
            if task_id in rec_stack:
                # Found a cycle
                cycle_start = path.index(task_id)
                cycles.append(tuple(path[cycle_start:] + [task_id]))
                return
            
            if task_id in visited:
                return
            
            visited.add(task_id)
            rec_stack.add(task_id)
            
            task = task_map.get(task_id)
            if task:
                for dep_id in task.get('dependencies', []):
                    if dep_id in task_map:
                        dfs(dep_id, path + [task_id])
            
            rec_stack.remove(task_id)
        
        for task_id in task_map:
            if task_id not in visited:
                dfs(task_id, [])
        
        return cycles
    
    def score_task(
        self, 
        task: Dict, 
        all_tasks: List[Dict],
        dependency_map: Optional[Dict[str, Set[str]]] = None
    ) -> Dict:
        """
        Calculate comprehensive priority score for a single task.
        
        Args:
            task: Task dictionary with required fields
            all_tasks: List of all tasks (for dependency calculation)
            dependency_map: Pre-built dependency map (optional optimization)
        
        Returns:
            Dictionary with score breakdown and total
        """
        if dependency_map is None:
            dependency_map = self.build_dependency_map(all_tasks)
        
        task_id = task.get('id', str(all_tasks.index(task)))
        
        # Calculate component scores
        # Support both old and new field names
        due_date = task.get('deadline') or task.get('due_date')
        urgency_score = self.calculate_urgency_score(due_date)
        importance = self.calculate_importance_score(task.get('importance'))
        effort_hours = task.get('effort') or task.get('estimated_hours')
        effort = self.calculate_effort_score(effort_hours)
        dependency = self.calculate_dependency_score(task_id, all_tasks, dependency_map)
        
        # Apply strategy weights
        weighted_urgency = urgency_score * self.weights['urgency']
        weighted_importance = importance * self.weights['importance']
        weighted_effort = effort * self.weights['effort']
        weighted_dependency = dependency * self.weights['dependency']
        
        total_score = (
            weighted_urgency + 
            weighted_importance + 
            weighted_effort + 
            weighted_dependency
        )
        
        return {
            'task': task,
            'score': round(total_score, 2),
            'breakdown': {
                'urgency': round(weighted_urgency, 2),
                'importance': round(weighted_importance, 2),
                'effort': round(weighted_effort, 2),
                'dependency': round(weighted_dependency, 2)
            },
            'raw_scores': {
                'urgency': round(urgency_score, 2),
                'importance': round(importance, 2),
                'effort': round(effort, 2),
                'dependency': round(dependency, 2)
            }
        }
    
    def analyze_tasks(self, tasks: List[Dict]) -> List[Dict]:
        """
        Score and sort all tasks by priority.
        
        Args:
            tasks: List of task dictionaries
        
        Returns:
            List of scored tasks sorted by priority (highest first)
        """
        if not tasks:
            return []
        
        # Ensure all tasks have IDs
        for i, task in enumerate(tasks):
            if 'id' not in task:
                task['id'] = f"task_{i}"
        
        # Build dependency map once for efficiency
        dependency_map = self.build_dependency_map(tasks)
        
        # Score all tasks
        scored_tasks = [
            self.score_task(task, tasks, dependency_map)
            for task in tasks
        ]
        
        # Sort by score descending
        scored_tasks.sort(key=lambda x: x['score'], reverse=True)
        
        return scored_tasks
    
    def suggest_top_tasks(self, tasks: List[Dict], count: int = 3) -> List[Dict]:
        """
        Suggest top N tasks with explanations.
        
        Args:
            tasks: List of task dictionaries
            count: Number of tasks to suggest
        
        Returns:
            List of top tasks with explanations
        """
        scored_tasks = self.analyze_tasks(tasks)
        top_tasks = scored_tasks[:count]
        
        # Add explanations
        for scored_task in top_tasks:
            explanation = self._generate_explanation(scored_task)
            scored_task['explanation'] = explanation
        
        return top_tasks
    
    def _generate_explanation(self, scored_task: Dict) -> str:
        """Generate human-readable explanation for task priority."""
        breakdown = scored_task['breakdown']
        raw = scored_task['raw_scores']
        task = scored_task['task']
        
        reasons = []
        
        # Urgency reasoning
        if raw['urgency'] >= 35:
            reasons.append("⚠️ Due very soon or overdue")
        elif raw['urgency'] >= 25:
            reasons.append("📅 Approaching deadline")
        
        # Importance reasoning
        if raw['importance'] >= 24:  # 8+ rating
            reasons.append("⭐ High importance rating")
        
        # Effort reasoning
        if raw['effort'] >= 12:  # Quick win
            reasons.append("⚡ Quick win (low effort)")
        
        # Dependency reasoning
        if raw['dependency'] >= 11:  # Blocks others
            reasons.append("🔗 Blocks other tasks")
        
        if not reasons:
            reasons.append("📊 Balanced priority across factors")
        
        return " • ".join(reasons)
