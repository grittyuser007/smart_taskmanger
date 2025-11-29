# tasks/tests.py
from django.test import TestCase
from datetime import datetime, timedelta
from ..tasks.scoring import TaskScorer


class TaskScorerTestCase(TestCase):
    """Comprehensive tests for the task scoring algorithm."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.scorer = TaskScorer(strategy='smart_balance')
        self.test_date = datetime(2025, 11, 29)
    
    def test_urgency_overdue_task(self):
        """Test that overdue tasks receive maximum urgency score."""
        overdue_date = "2025-11-20"  # 9 days overdue
        score = self.scorer.calculate_urgency_score(overdue_date, self.test_date)
        self.assertGreaterEqual(score, 38, "Overdue tasks should have high urgency")
    
    def test_urgency_due_today(self):
        """Test tasks due today get very high urgency."""
        today = "2025-11-29"
        score = self.scorer.calculate_urgency_score(today, self.test_date)
        self.assertEqual(score, 38, "Tasks due today should have urgency score of 38")
    
    def test_urgency_future_task(self):
        """Test that far future tasks have lower urgency."""
        future_date = "2025-12-29"  # 30 days away
        score = self.scorer.calculate_urgency_score(future_date, self.test_date)
        self.assertLess(score, 10, "Tasks 30 days out should have low urgency")
    
    def test_urgency_no_due_date(self):
        """Test handling of tasks without due dates."""
        score = self.scorer.calculate_urgency_score(None, self.test_date)
        self.assertEqual(score, 10, "Tasks without due dates should get default score")
    
    def test_urgency_invalid_date(self):
        """Test handling of invalid date formats."""
        invalid_date = "not-a-date"
        score = self.scorer.calculate_urgency_score(invalid_date, self.test_date)
        self.assertEqual(score, 10, "Invalid dates should return default score")
    
    def test_importance_valid_range(self):
        """Test importance scoring within valid range."""
        for importance in range(1, 11):
            score = self.scorer.calculate_importance_score(importance)
            expected = importance * 3
            self.assertEqual(score, expected, 
                           f"Importance {importance} should map to {expected}")
    
    def test_importance_out_of_range(self):
        """Test that importance values are clamped to valid range."""
        score_high = self.scorer.calculate_importance_score(15)
        score_low = self.scorer.calculate_importance_score(-5)
        self.assertEqual(score_high, 30, "High values should be clamped to max")
        self.assertEqual(score_low, 3, "Low values should be clamped to min")
    
    def test_importance_none_value(self):
        """Test handling of missing importance."""
        score = self.scorer.calculate_importance_score(None)
        self.assertEqual(score, 15, "None importance should return mid-range default")
    
    def test_effort_quick_wins(self):
        """Test that quick tasks (1 hour or less) get highest effort scores."""
        score = self.scorer.calculate_effort_score(0.5)
        self.assertEqual(score, 15, "Tasks under 1 hour should get maximum effort score")
    
    def test_effort_long_tasks(self):
        """Test that long tasks get lower effort scores."""
        score = self.scorer.calculate_effort_score(10)
        self.assertLess(score, 7, "10-hour tasks should have low effort scores")
    
    def test_effort_none_value(self):
        """Test handling of missing effort estimation."""
        score = self.scorer.calculate_effort_score(None)
        self.assertEqual(score, 7.5, "None effort should return mid-range default")
    
    def test_effort_zero_or_negative(self):
        """Test handling of invalid effort values."""
        score_zero = self.scorer.calculate_effort_score(0)
        score_negative = self.scorer.calculate_effort_score(-5)
        self.assertEqual(score_zero, 7.5, "Zero effort should return default")
        self.assertEqual(score_negative, 7.5, "Negative effort should return default")
    
    def test_dependency_map_building(self):
        """Test that dependency map is built correctly."""
        tasks = [
            {"id": "task_1", "dependencies": []},
            {"id": "task_2", "dependencies": ["task_1"]},
            {"id": "task_3", "dependencies": ["task_1"]},
        ]
        
        dep_map = self.scorer.build_dependency_map(tasks)
        
        self.assertIn("task_1", dep_map)
        self.assertEqual(len(dep_map["task_1"]), 2, 
                        "task_1 should have 2 dependents")
        self.assertIn("task_2", dep_map["task_1"])
        self.assertIn("task_3", dep_map["task_1"])
    
    def test_dependency_score_blocking_tasks(self):
        """Test that tasks blocking others get higher scores."""
        tasks = [
            {"id": "task_1", "dependencies": []},
            {"id": "task_2", "dependencies": ["task_1"]},
            {"id": "task_3", "dependencies": ["task_1"]},
        ]
        
        dep_map = self.scorer.build_dependency_map(tasks)
        score = self.scorer.calculate_dependency_score("task_1", tasks, dep_map)
        
        self.assertGreaterEqual(score, 11, 
                               "Tasks blocking 2 others should score >= 11")
    
    def test_dependency_score_no_dependents(self):
        """Test tasks with no dependents get baseline score."""
        tasks = [
            {"id": "task_1", "dependencies": []},
            {"id": "task_2", "dependencies": []},
        ]
        
        dep_map = self.scorer.build_dependency_map(tasks)
        score = self.scorer.calculate_dependency_score("task_1", tasks, dep_map)
        
        self.assertEqual(score, 5, "Tasks with no dependents should score 5")
    
    def test_circular_dependency_detection(self):
        """Test detection of circular dependencies."""
        tasks = [
            {"id": "task_1", "dependencies": ["task_2"]},
            {"id": "task_2", "dependencies": ["task_3"]},
            {"id": "task_3", "dependencies": ["task_1"]},
        ]
        
        cycles = self.scorer.detect_circular_dependencies(tasks)
        
        self.assertGreater(len(cycles), 0, "Should detect circular dependency")
        # Verify cycle contains all three tasks
        cycle = cycles[0]
        self.assertIn("task_1", cycle)
        self.assertIn("task_2", cycle)
        self.assertIn("task_3", cycle)
    
    def test_no_circular_dependencies(self):
        """Test that valid dependency chains don't trigger false positives."""
        tasks = [
            {"id": "task_1", "dependencies": []},
            {"id": "task_2", "dependencies": ["task_1"]},
            {"id": "task_3", "dependencies": ["task_2"]},
        ]
        
        cycles = self.scorer.detect_circular_dependencies(tasks)
        
        self.assertEqual(len(cycles), 0, "Should not detect cycles in valid chain")
    
    def test_score_task_comprehensive(self):
        """Test comprehensive scoring of a single task."""
        tasks = [
            {
                "id": "task_1",
                "title": "Fix critical bug",
                "due_date": "2025-11-30",
                "estimated_hours": 2,
                "importance": 9,
                "dependencies": []
            }
        ]
        
        result = self.scorer.score_task(tasks[0], tasks)
        
        self.assertIn('score', result)
        self.assertIn('breakdown', result)
        self.assertIn('raw_scores', result)
        self.assertGreater(result['score'], 0)
        
        # Verify all components are present
        breakdown = result['breakdown']
        self.assertIn('urgency', breakdown)
        self.assertIn('importance', breakdown)
        self.assertIn('effort', breakdown)
        self.assertIn('dependency', breakdown)
    
    def test_analyze_tasks_sorting(self):
        """Test that tasks are sorted correctly by priority."""
        tasks = [
            {
                "id": "task_1",
                "title": "Low priority",
                "due_date": "2025-12-30",
                "estimated_hours": 10,
                "importance": 3,
                "dependencies": []
            },
            {
                "id": "task_2",
                "title": "High priority",
                "due_date": "2025-11-30",
                "estimated_hours": 1,
                "importance": 10,
                "dependencies": []
            },
            {
                "id": "task_3",
                "title": "Medium priority",
                "due_date": "2025-12-10",
                "estimated_hours": 4,
                "importance": 6,
                "dependencies": []
            }
        ]
        
        scored_tasks = self.scorer.analyze_tasks(tasks)
        
        # Verify sorting
        self.assertEqual(len(scored_tasks), 3)
        self.assertGreaterEqual(scored_tasks[0]['score'], scored_tasks[1]['score'])
        self.assertGreaterEqual(scored_tasks[1]['score'], scored_tasks[2]['score'])
        
        # High priority task should be first
        self.assertEqual(scored_tasks[0]['task']['id'], "task_2")
    
    def test_analyze_empty_task_list(self):
        """Test handling of empty task list."""
        result = self.scorer.analyze_tasks([])
        self.assertEqual(result, [], "Empty task list should return empty result")
    
    def test_strategy_fastest_wins(self):
        """Test that fastest_wins strategy prioritizes low-effort tasks."""
        tasks = [
            {
                "id": "task_1",
                "title": "Long task",
                "due_date": "2025-12-05",
                "estimated_hours": 8,
                "importance": 8,
                "dependencies": []
            },
            {
                "id": "task_2",
                "title": "Quick task",
                "due_date": "2025-12-05",
                "estimated_hours": 1,
                "importance": 8,
                "dependencies": []
            }
        ]
        
        scorer = TaskScorer(strategy='fastest_wins')
        scored_tasks = scorer.analyze_tasks(tasks)
        
        # Quick task should rank higher with fastest_wins strategy
        self.assertEqual(scored_tasks[0]['task']['id'], "task_2",
                        "Fastest wins should prioritize quick tasks")
    
    def test_strategy_high_impact(self):
        """Test that high_impact strategy prioritizes importance."""
        tasks = [
            {
                "id": "task_1",
                "title": "Important task",
                "due_date": "2025-12-20",
                "estimated_hours": 5,
                "importance": 10,
                "dependencies": []
            },
            {
                "id": "task_2",
                "title": "Urgent task",
                "due_date": "2025-11-30",
                "estimated_hours": 5,
                "importance": 5,
                "dependencies": []
            }
        ]
        
        scorer = TaskScorer(strategy='high_impact')
        scored_tasks = scorer.analyze_tasks(tasks)
        
        # Important task should rank higher with high_impact strategy
        self.assertEqual(scored_tasks[0]['task']['id'], "task_1",
                        "High impact should prioritize importance")
    
    def test_strategy_deadline_driven(self):
        """Test that deadline_driven strategy prioritizes urgency."""
        tasks = [
            {
                "id": "task_1",
                "title": "Important but not urgent",
                "due_date": "2025-12-20",
                "estimated_hours": 3,
                "importance": 10,
                "dependencies": []
            },
            {
                "id": "task_2",
                "title": "Less important but urgent",
                "due_date": "2025-11-30",
                "estimated_hours": 3,
                "importance": 5,
                "dependencies": []
            }
        ]
        
        scorer = TaskScorer(strategy='deadline_driven')
        scored_tasks = scorer.analyze_tasks(tasks)
        
        # Urgent task should rank higher with deadline_driven strategy
        self.assertEqual(scored_tasks[0]['task']['id'], "task_2",
                        "Deadline driven should prioritize urgency")
    
    def test_suggest_top_tasks(self):
        """Test top task suggestions with explanations."""
        tasks = [
            {
                "id": "task_1",
                "title": "Task 1",
                "due_date": "2025-11-30",
                "estimated_hours": 2,
                "importance": 8,
                "dependencies": []
            },
            {
                "id": "task_2",
                "title": "Task 2",
                "due_date": "2025-12-10",
                "estimated_hours": 5,
                "importance": 6,
                "dependencies": []
            }
        ]
        
        suggestions = self.scorer.suggest_top_tasks(tasks, count=2)
        
        self.assertEqual(len(suggestions), 2)
        for suggestion in suggestions:
            self.assertIn('explanation', suggestion)
            self.assertIn('score', suggestion)
            self.assertIn('task', suggestion)
            self.assertIsInstance(suggestion['explanation'], str)
            self.assertGreater(len(suggestion['explanation']), 0)
    
    def test_tasks_without_ids_get_assigned(self):
        """Test that tasks without IDs are assigned default IDs."""
        tasks = [
            {
                "title": "Task without ID",
                "due_date": "2025-12-05",
                "estimated_hours": 3,
                "importance": 7,
                "dependencies": []
            }
        ]
        
        scored_tasks = self.scorer.analyze_tasks(tasks)
        
        self.assertEqual(len(scored_tasks), 1)
        self.assertIn('id', scored_tasks[0]['task'])
        self.assertTrue(scored_tasks[0]['task']['id'].startswith('task_'))