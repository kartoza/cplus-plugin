import os
import unittest
import uuid
from unittest.mock import patch, MagicMock
from cplus_plugin.api.scenario_history_tasks import (
    FetchScenarioHistoryTask,
    FetchScenarioOutputTask,
    DeleteScenarioTask,
)
from cplus_plugin.api.request import CplusApiRequest
from cplus_core.models.base import Scenario, SpatialExtent
from cplus_core.analysis import TaskConfig


class TestFetchScenarioHistoryTask(unittest.TestCase):
    """Test class to fetch scenario history task."""

    @patch(
        "cplus_plugin.api.scenario_history_tasks.CplusApiRequest.fetch_scenario_history"
    )
    @patch("cplus_plugin.api.scenario_history_tasks.settings_manager.get_scenarios")
    @patch("cplus_plugin.api.scenario_history_tasks.settings_manager.save_scenario")
    @patch("cplus_plugin.api.scenario_history_tasks.settings_manager.delete_scenario")
    def test_run_success(
        self,
        mock_delete_scenario,
        mock_save_scenario,
        mock_get_scenarios,
        mock_fetch_scenario_history,
    ):
        # Setup mock data
        mock_fetch_scenario_history.return_value = [
            Scenario(
                uuid=uuid.uuid4(),
                name="Scenario A",
                description="Scenario description",
                activities=[],
                extent=SpatialExtent([]),
                weighted_activities=[],
                priority_layer_groups=[],
                server_uuid=uuid.uuid4(),
            )
        ]
        mock_get_scenarios.return_value = [
            Scenario(
                uuid=uuid.uuid4(),
                name="Scenario B",
                description="Scenario description",
                activities=[],
                extent=SpatialExtent([]),
                weighted_activities=[],
                priority_layer_groups=[],
                server_uuid=uuid.uuid4(),
            )
        ]

        task = FetchScenarioHistoryTask()
        result = task.run()
        self.assertTrue(result)
        task.finished(result)
        mock_fetch_scenario_history.assert_called_once()
        mock_save_scenario.assert_called_once()
        mock_delete_scenario.assert_called_once()

    @patch(
        "cplus_plugin.api.scenario_history_tasks.CplusApiRequest.fetch_scenario_history"
    )
    @patch("cplus_plugin.api.scenario_history_tasks.log")
    def test_run_failure(self, mock_log, mock_fetch_scenario_history):
        # Setup mock to raise exception
        mock_fetch_scenario_history.side_effect = Exception("API Error")

        task = FetchScenarioHistoryTask()
        result = task.run()

        self.assertFalse(result)
        mock_log.assert_called_with(
            "Error during fetch scenario history: API Error", info=False
        )


class TestFetchScenarioOutputTask(unittest.TestCase):
    """Test class to fetch/download scenario output task."""

    @patch(
        "cplus_plugin.api.scenario_history_tasks.CplusApiRequest.fetch_scenario_output_list"
    )
    @patch(
        "cplus_plugin.api.scenario_history_tasks.CplusApiRequest.fetch_scenario_detail"
    )
    @patch("cplus_plugin.api.request.CplusApiPooling.results")
    @patch("cplus_plugin.api.scenario_history_tasks.settings_manager.save_scenario")
    @patch(
        "cplus_plugin.api.scenario_history_tasks.settings_manager.save_scenario_result"
    )
    def test_run_success(
        self,
        mock_save_scenario_result,
        mock_save_scenario,
        mock_cplus_pooling_results,
        mock_fetch_scenario_detail,
        mock_fetch_scenario_output_list,
    ):
        # Setup mock data
        mock_fetch_scenario_detail.return_value = {
            "submitted_on": "2023-01-01T00:00:00Z",
            "updated_detail": {
                "activities": [],
                "weighted_activities": [],
                "priority_layer_groups": [],
            },
        }
        mock_cplus_pooling_results.return_value = {
            "progress_text": "Complete",
            "progress": 100,
            "logs": [
                {"log": "Log 1", "date_time": "2023-01-01T00:00:05Z"},
                {"log": "Log 2", "date_time": "2023-01-01T00:00:10Z"},
            ],
        }
        mock_fetch_scenario_output_list.return_value = {
            "results": [
                {
                    "url": "http://example.com/file",
                    "filename": "output.txt",
                    "is_final_output": True,
                }
            ]
        }

        scenario = Scenario(
            uuid=uuid.uuid4(),
            name="Scenario A",
            description="Scenario description",
            activities=[],
            extent=SpatialExtent([]),
            weighted_activities=[],
            priority_layer_groups=[],
            server_uuid=uuid.uuid4(),
        )
        analysis_scenario_name = scenario.name
        analysis_scenario_description = scenario.description
        analysis_extent = SpatialExtent(bbox=scenario.extent.bbox)
        analysis_activities = scenario.activities
        analysis_priority_layers_groups = scenario.priority_layer_groups
        task_config = TaskConfig(
            scenario,
            [],
            analysis_priority_layers_groups,
            analysis_activities,
            analysis_activities,
            pathway_suitability_index=1.0,
            carbon_coefficient=1.0,
            base_dir=os.path.join("/tmp", str(scenario.uuid)),
        )
        task = FetchScenarioOutputTask(task_config, None)

        with patch.object(
            FetchScenarioOutputTask, "fetch_scenario_output"
        ) as mock_fetch_output:
            with patch.object(
                FetchScenarioOutputTask, "delete_online_task"
            ) as mock_delete_online_task:
                mock_fetch_output.return_value = (scenario, MagicMock())
                result = task.run()
                task.finished(result)

        self.assertTrue(result)
        mock_save_scenario.assert_called_once()
        mock_save_scenario_result.assert_called_once()

    @patch("cplus_plugin.api.scenario_history_tasks.log")
    def test_run_failure(self, mock_log):
        # Setup mock to raise exception
        scenario = Scenario(
            uuid=uuid.uuid4(),
            name="Scenario A",
            description="Scenario description",
            activities=[],
            extent=SpatialExtent([]),
            weighted_activities=[],
            priority_layer_groups=[],
            server_uuid=uuid.uuid4(),
        )
        analysis_scenario_name = scenario.name
        analysis_scenario_description = scenario.description
        analysis_extent = SpatialExtent(bbox=scenario.extent.bbox)
        analysis_activities = scenario.activities
        analysis_priority_layers_groups = scenario.priority_layer_groups
        task_config = TaskConfig(
            scenario,
            [],
            analysis_priority_layers_groups,
            analysis_activities,
            analysis_activities,
            pathway_suitability_index=1.0,
            carbon_coefficient=1.0,
            base_dir=os.path.join("/tmp", str(scenario.uuid)),
        )
        task = FetchScenarioOutputTask(task_config, None)

        with patch.object(
            CplusApiRequest,
            "fetch_scenario_status",
            side_effect=Exception("API Error"),
        ):
            result = task.run()

        self.assertFalse(result)
        mock_log.assert_called_with(
            "Error during fetch scenario output list: API Error", info=False
        )


class TestDeleteScenarioTask(unittest.TestCase):
    """Test class for delete scenario task."""

    @patch("cplus_plugin.api.scenario_history_tasks.CplusApiRequest.delete_scenario")
    def test_run_success(self, mock_delete_scenario):
        # Setup mock to simulate successful deletion
        task = DeleteScenarioTask(scenario_server_uuid="123")
        result = task.run()
        self.assertTrue(result)
        mock_delete_scenario.assert_called_once_with("123")

    @patch("cplus_plugin.api.scenario_history_tasks.CplusApiRequest.delete_scenario")
    @patch("cplus_plugin.api.scenario_history_tasks.log")
    def test_run_failure(self, mock_log, mock_delete_scenario):
        # Setup mock to raise exception
        mock_delete_scenario.side_effect = Exception("API Error")

        task = DeleteScenarioTask(scenario_server_uuid="123")
        result = task.run()

        self.assertFalse(result)
        mock_log.assert_called_with(
            "Error during delete scenario: API Error", info=False
        )
