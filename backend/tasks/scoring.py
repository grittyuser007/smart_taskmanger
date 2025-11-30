# tasks/scoring.py
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
import math

try:
    import holidays
    HOLIDAYS_AVAILABLE = True
except ImportError:
    HOLIDAYS_AVAILABLE = False


class TaskScorer:
    """
    Intelligent task priority scoring system that balances multiple factors.
    
    Scoring Components:
    - Urgency Score (0-40): Based on working days until due date
    - Importance Score (0-30): Direct mapping from user rating
    - Effort Score (0-15): Inverse relationship - quick wins get higher scores
    - Dependency Score (0-15): Tasks blocking others rank higher
    
    Total possible score: 100 points
    """
    
    def __init__(self, strategy='smart_balance', country='IN', consider_holidays=True):
        """
        Initialize scorer with a specific strategy.
        
        Args:
            strategy: 'fastest_wins', 'high_impact', 'deadline_driven', or 'smart_balance'
            country: Country code for holidays ('IN', 'US', 'GB', etc.)
            consider_holidays: Whether to exclude weekends/holidays in urgency calculation
        """
        self.strategy = strategy
        self.country = country
        self.consider_holidays = consider_holidays and HOLIDAYS_AVAILABLE
        self.weights = self._get_strategy_weights()
        
        # Initialize holidays if available
        if self.consider_holidays:
            self.country_holidays = holidays.country_holidays(country)
        else:
            self.country_holidays = None
    
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
    
    def _calculate_working_days(self, start_date, end_date) -> int:
        """
        Calculate number of working days between two dates.
        Excludes weekends and public holidays if holiday support is enabled.
        
        Args:
            start_date: Start date
            end_date: End date
        
        Returns:
            Number of working days (can be negative if overdue)
        """
        if end_date < start_date:
            # Calculate overdue working days
            return -self._calculate_working_days(end_date, start_date)
        
        if not self.consider_holidays:
            # Fall back to calendar days
            return (end_date - start_date).days
        
        working_days = 0
        current = start_date
        
        while current < end_date:
            # Skip weekends (Saturday=5, Sunday=6)
            if current.weekday() < 5:  # Monday=0 to Friday=4
                # Skip public holidays
                if current not in self.country_holidays:
                    working_days += 1
            current += timedelta(days=1)
        
        return working_days
    
    def calculate_urgency_score(self, due_date: Optional[str], current_date: datetime = None) -> float:
        """
        Calculate urgency score based on working days until due date.
        
        Scoring logic:
        - Overdue: 40 points (maximum urgency)
        - Due today: 38 points
        - Due in 1-2 working days: 35-33 points (steep curve)
        - Due in 3-5 working days: 30-25 points
        - Due in 6-10 working days: 20-15 points
        - Due in 11+ working days: <15 points (exponential decay)
        
        Args:
            due_date: ISO format date string (YYYY-MM-DD) or datetime string
            current_date: Reference date (defaults to now)
        
        Returns:
            Urgency score (0-40)
        """
        if not due_date:
            return 10  # Default score for tasks without due dates
        
        if current_date is None:
            current_date = datetime.now()
        
        try:
            # Handle both date strings and datetime strings
            if isinstance(due_date, str):
                # Try to parse as datetime first, then fall back to date
                try:
                    due = datetime.fromisoformat(due_date.replace('Z', '+00:00'))
                except ValueError:
                    due = datetime.strptime(due_date, '%Y-%m-%d')
            else:
                due = due_date
            
            # Calculate working days or calendar days
            if self.consider_holidays:
                days_until_due = self._calculate_working_days(current_date.date(), due.date())
            else:
                days_until_due = (due.date() - current_date.date()).days
            
            # Overdue tasks get maximum urgency
            if days_until_due < 0:
                overdue_days = abs(days_until_due)
                # More overdue = higher urgency (capped at 40)
                return min(40, 40 + (overdue_days * 0.5))
            
            # Due today
            if days_until_due == 0:
                return 38
            
            # Scoring based on working days remaining
            if days_until_due == 1:
                return 35
            elif days_until_due == 2:
                return 33
            elif days_until_due <= 5:  # 3-5 working days
                return 30 - ((days_until_due - 2) * 2)
            elif days_until_due <= 10:  # 6-10 working days (1-2 weeks)
                return 20 - ((days_until_due - 5))
            elif days_until_due <= 15:  # 11-15 working days (2-3 weeks)
                return 15 - ((days_until_due - 10) * 0.8)
            else:  # 15+ working days
                # Asymptotic approach to 0 for far future tasks
                return max(0, 5 - (days_until_due - 15) * 0.3)
        
        except (ValueError, TypeError) as e:
            print(f"Error parsing date {due_date}: {e}")
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
        dependent_count = len(dependency_map.get(str(task_id), set()))
        
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
        
        Args:
            tasks: List of task dictionaries
        
        Returns:
            Dictionary mapping task IDs to their dependents
        """
        dependency_map = {}
        task_ids = {str(task.get('id', str(i))) for i, task in enumerate(tasks)}
        
        for i, task in enumerate(tasks):
            task_id = str(task.get('id', str(i)))
            dependencies = task.get('dependencies', [])
            
            if dependencies:
                for dep_id in dependencies:
                    dep_id_str = str(dep_id)
                    # Validate dependency exists
                    if dep_id_str in task_ids:
                        if dep_id_str not in dependency_map:
                            dependency_map[dep_id_str] = set()
                        dependency_map[dep_id_str].add(task_id)
        
        return dependency_map
    
    def detect_circular_dependencies(self, tasks: List[Dict]) -> List[tuple]:
        """
        Detect circular dependencies using depth-first search.
        
        Returns list of cycles found as tuples of task IDs.
        """
        task_map = {str(task.get('id', str(i))): task for i, task in enumerate(tasks)}
        visited = set()
        rec_stack = set()
        cycles = []
        
        def dfs(task_id: str, path: List[str]):
            if task_id in rec_stack:
                # Found a cycle
                try:
                    cycle_start = path.index(task_id)
                    cycles.append(tuple(path[cycle_start:] + [task_id]))
                except ValueError:
                    pass
                return
            
            if task_id in visited:
                return
            
            visited.add(task_id)
            rec_stack.add(task_id)
            
            task = task_map.get(task_id)
            if task:
                dependencies = task.get('dependencies', [])
                if dependencies:
                    for dep_id in dependencies:
                        dep_id_str = str(dep_id)
                        if dep_id_str in task_map:
                            dfs(dep_id_str, path + [task_id])
            
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
        
        task_id = str(task.get('id', str(all_tasks.index(task))))
        
        # Calculate component scores
        # Support both field name conventions
        due_date = task.get('due_date')
        estimated_hours = task.get('estimated_hours') or task.get('effort')
        
        urgency = self.calculate_urgency_score(due_date)
        importance = self.calculate_importance_score(task.get('importance'))
        effort = self.calculate_effort_score(estimated_hours)
        dependency = self.calculate_dependency_score(task_id, all_tasks, dependency_map)
        
        # Apply strategy weights
        weighted_urgency = urgency * self.weights['urgency']
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
                'urgency': round(urgency, 2),
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