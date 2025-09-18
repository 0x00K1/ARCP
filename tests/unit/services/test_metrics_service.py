"""
Unit tests for ARCP metrics service module.

This test module comprehensively tests metrics collection, Prometheus integration,
system resource monitoring, and agent metrics aggregation.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from src.arcp.services.metrics import MetricsService, get_metrics_service


@pytest.mark.unit
class TestMetricsServiceInitialization:
    """Test cases for MetricsService initialization."""

    @patch("src.arcp.services.metrics.PROMETHEUS_AVAILABLE", False)
    @patch("src.arcp.services.metrics.PSUTIL_AVAILABLE", False)
    def test_initialization_no_dependencies(self):
        """Test initialization when optional dependencies are not available."""
        service = MetricsService()

        assert service._prometheus_available is False
        assert service._psutil_available is False
        assert service.is_prometheus_available() is False
        assert service.is_psutil_available() is False

    @patch("src.arcp.services.metrics.PROMETHEUS_AVAILABLE", True)
    @patch("src.arcp.services.metrics.PSUTIL_AVAILABLE", True)
    def test_initialization_with_dependencies(self):
        """Test initialization when all dependencies are available."""
        service = MetricsService()

        assert service._prometheus_available is True
        assert service._psutil_available is True
        assert service.is_prometheus_available() is True
        assert service.is_psutil_available() is True

    @patch("src.arcp.services.metrics.PROMETHEUS_AVAILABLE", True)
    @patch("src.arcp.services.metrics.PSUTIL_AVAILABLE", False)
    def test_initialization_partial_dependencies(self):
        """Test initialization with partial dependency availability."""
        service = MetricsService()

        assert service._prometheus_available is True
        assert service._psutil_available is False


@pytest.mark.unit
class TestPrometheusMetrics:
    """Test cases for Prometheus metrics functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = MetricsService()

    @patch("src.arcp.services.metrics.PROMETHEUS_AVAILABLE", False)
    def test_get_prometheus_metrics_unavailable(self):
        """Test Prometheus metrics when client is not available."""
        self.service._prometheus_available = False

        data, content_type = self.service.get_prometheus_metrics()

        assert content_type == "text/plain"
        assert b"prometheus-client not available" in data

    @patch("src.arcp.services.metrics.PROMETHEUS_AVAILABLE", True)
    @patch("src.arcp.services.metrics.generate_latest")
    def test_get_prometheus_metrics_success(self, mock_generate):
        """Test successful Prometheus metrics generation."""
        self.service._prometheus_available = True
        mock_generate.return_value = (
            b"# HELP test_metric A test metric\ntest_metric 1.0\n"
        )

        data, content_type = self.service.get_prometheus_metrics()

        assert (
            content_type == "text/plain; version=0.0.4; charset=utf-8"
        )  # Updated to actual content type
        assert b"test_metric 1.0" in data
        mock_generate.assert_called_once()

    @patch("src.arcp.services.metrics.PROMETHEUS_AVAILABLE", True)
    @patch("src.arcp.services.metrics.generate_latest")
    def test_get_prometheus_metrics_error(self, mock_generate):
        """Test Prometheus metrics generation error handling."""
        self.service._prometheus_available = True
        mock_generate.side_effect = Exception("Metrics collection failed")

        data, content_type = self.service.get_prometheus_metrics()

        assert b"metrics temporarily unavailable" in data
        assert "Metrics collection failed" in data.decode()
        # Content type should still be CONTENT_TYPE_LATEST for proper parsing
        assert (
            "openmetrics-text" in content_type
            or content_type == "text/plain; version=0.0.4; charset=utf-8"
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestResourceUtilization:
    """Test cases for system resource utilization monitoring."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = MetricsService()

    @patch("src.arcp.services.metrics.PSUTIL_AVAILABLE", False)
    async def test_get_resource_utilization_unavailable(self):
        """Test resource utilization when psutil is not available."""
        self.service._psutil_available = False

        metrics = await self.service.get_resource_utilization()

        assert metrics["cpu"] == 0.0
        assert metrics["memory"] == 0.0
        assert metrics["network"] == 0.0
        assert metrics["storage"] == 0.0

    @patch("src.arcp.services.metrics.PSUTIL_AVAILABLE", True)
    @patch("src.arcp.services.metrics.psutil")
    async def test_get_resource_utilization_success(self, mock_psutil):
        """Test successful resource utilization collection."""
        self.service._psutil_available = True

        # Mock psutil functions
        mock_psutil.cpu_percent.return_value = 45.5

        mock_memory = MagicMock()
        mock_memory.percent = 67.2
        mock_psutil.virtual_memory.return_value = mock_memory

        mock_net_io = MagicMock()
        mock_net_io.bytes_sent = 1024 * 1024 * 10  # 10 MB
        mock_net_io.bytes_recv = 1024 * 1024 * 20  # 20 MB
        mock_psutil.net_io_counters.return_value = mock_net_io

        mock_disk = MagicMock()
        mock_disk.percent = 82.1
        mock_psutil.disk_usage.return_value = mock_disk

        # Mock disk_io_counters to return None to avoid I/O calculation
        mock_psutil.disk_io_counters.return_value = None

        # Note: Network will be 0.0 without previous data for comparison

        metrics = await self.service.get_resource_utilization()

        assert metrics["cpu"] == 45.5
        assert metrics["memory"] == 67.2
        assert metrics["network"] == 0.0  # No previous data for rate calculation
        assert (
            metrics["storage"] == 57.47
        )  # (82.1 * 0.7) + (0 * 0.3) = weighted calculation

        mock_psutil.cpu_percent.assert_called_once_with(interval=None)
        mock_psutil.virtual_memory.assert_called_once()
        mock_psutil.net_io_counters.assert_called_once()
        mock_psutil.disk_usage.assert_called_once_with("/")
        mock_psutil.disk_io_counters.assert_called_once()

    @patch("src.arcp.services.metrics.PSUTIL_AVAILABLE", True)
    @patch("src.arcp.services.metrics.psutil")
    async def test_get_resource_utilization_error(self, mock_psutil):
        """Test resource utilization error handling."""
        self.service._psutil_available = True
        mock_psutil.cpu_percent.side_effect = Exception("CPU monitoring failed")
        mock_psutil.virtual_memory.side_effect = Exception("Memory monitoring failed")
        mock_psutil.net_io_counters.side_effect = Exception("Network monitoring failed")
        mock_psutil.disk_usage.side_effect = Exception("Disk monitoring failed")

        metrics = await self.service.get_resource_utilization()

        # Should return zero values on error
        assert metrics["cpu"] == 0.0
        assert metrics["memory"] == 0.0
        assert metrics["network"] == 0.0
        assert metrics["storage"] == 0.0

    @patch("src.arcp.services.metrics.PSUTIL_AVAILABLE", True)
    @patch("src.arcp.services.metrics.psutil")
    async def test_get_resource_utilization_network_calculation(self, mock_psutil):
        """Test network utilization calculation edge cases."""
        self.service._psutil_available = True

        # Mock other metrics
        mock_psutil.cpu_percent.return_value = 0
        mock_psutil.virtual_memory.return_value = MagicMock(percent=0)
        mock_psutil.disk_usage.return_value = MagicMock(percent=0)

        # Test very large network usage
        mock_net_io = MagicMock()
        mock_net_io.bytes_sent = 1024 * 1024 * 1024 * 200  # 200 GB
        mock_net_io.bytes_recv = 1024 * 1024 * 1024 * 300  # 300 GB
        mock_psutil.net_io_counters.return_value = mock_net_io

        # Setup previous data for network calculation
        import time

        current_time = time.time()
        self.service._memory_cache["network"] = {
            "timestamp": current_time - 1.0,  # 1 second ago
            "bytes": 0,  # Previous total bytes
        }

        metrics = await self.service.get_resource_utilization()

        # Network should be capped at 100.0
        assert metrics["network"] == 100.0


@pytest.mark.unit
class TestAgentMetricsSummary:
    """Test cases for agent metrics aggregation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = MetricsService()

    def test_calculate_agent_metrics_summary_empty(self):
        """Test metrics summary with empty input."""
        result = self.service.calculate_agent_metrics_summary([])

        assert result["total_requests"] == 0
        assert result["avg_response_time"] == 0.0
        assert result["error_rate"] == 0.0
        assert result["agent_count"] == 0

    def test_calculate_agent_metrics_summary_single_agent(self):
        """Test metrics summary with single agent."""
        # Mock agent metrics object
        mock_metrics = MagicMock()
        mock_metrics.dict.return_value = {
            "total_requests": 100,
            "avg_response_time": 0.5,
            "success_rate": 0.95,
        }

        result = self.service.calculate_agent_metrics_summary([mock_metrics])

        assert result["total_requests"] == 100
        assert result["avg_response_time"] == 0.5
        assert result["error_rate"] == 0.05  # 1 - success_rate
        assert result["agent_count"] == 1

    def test_calculate_agent_metrics_summary_multiple_agents(self):
        """Test metrics summary with multiple agents."""
        # Create mock metrics for multiple agents
        mock_metrics_1 = MagicMock()
        mock_metrics_1.dict.return_value = {
            "total_requests": 100,
            "avg_response_time": 0.4,
            "success_rate": 0.9,
        }

        mock_metrics_2 = MagicMock()
        mock_metrics_2.dict.return_value = {
            "total_requests": 200,
            "avg_response_time": 0.6,
            "success_rate": 0.95,
        }

        result = self.service.calculate_agent_metrics_summary(
            [mock_metrics_1, mock_metrics_2]
        )

        assert result["total_requests"] == 300
        # Weighted average: (0.4*100 + 0.6*200) / 300 = 0.533...
        assert abs(result["avg_response_time"] - 0.533) < 0.001
        # Error rate: ((1-0.9)*100 + (1-0.95)*200) / 300 = 20/300 = 0.0667
        assert abs(result["error_rate"] - 0.0667) < 0.001
        assert result["agent_count"] == 2

    def test_calculate_agent_metrics_summary_dict_objects(self):
        """Test metrics summary with dict objects instead of model objects."""
        metrics_data = [
            {
                "total_requests": 50,
                "avg_response_time": 0.3,
                "success_rate": 1.0,
            },
            {
                "total_requests": 150,
                "average_response_time": 0.7,  # Alternative field name
                "success_rate": 0.8,
            },
        ]

        # Mock objects that don't have dict() method but have __dict__
        mock_metrics = []
        for data in metrics_data:
            mock_obj = MagicMock()
            mock_obj.dict.side_effect = AttributeError("no dict method")
            mock_obj.__dict__ = data
            mock_metrics.append(mock_obj)

        result = self.service.calculate_agent_metrics_summary(mock_metrics)

        assert result["total_requests"] == 200
        # Should handle alternative field names
        # Weighted average: (0.3*50 + 0.7*150) / 200 = 0.6
        assert abs(result["avg_response_time"] - 0.6) < 0.001
        assert result["agent_count"] == 2

    def test_calculate_agent_metrics_summary_zero_requests(self):
        """Test metrics summary with agents having zero requests."""
        mock_metrics = MagicMock()
        mock_metrics.dict.return_value = {
            "total_requests": 0,
            "avg_response_time": 0,
            "success_rate": 1.0,
        }

        result = self.service.calculate_agent_metrics_summary([mock_metrics])

        assert result["total_requests"] == 0
        assert result["avg_response_time"] == 0.0
        assert result["error_rate"] == 0.0
        assert result["agent_count"] == 1

    def test_calculate_agent_metrics_summary_missing_fields(self):
        """Test metrics summary with missing fields."""
        mock_metrics = MagicMock()
        mock_metrics.dict.return_value = {}  # Empty dict

        result = self.service.calculate_agent_metrics_summary([mock_metrics])

        assert result["total_requests"] == 0
        assert result["avg_response_time"] == 0.0
        assert result["error_rate"] == 0.0
        assert result["agent_count"] == 1

    def test_calculate_agent_metrics_summary_none_values(self):
        """Test metrics summary with None values."""
        mock_metrics = MagicMock()
        mock_metrics.dict.return_value = {
            "total_requests": None,
            "avg_response_time": None,
            "success_rate": None,
        }

        result = self.service.calculate_agent_metrics_summary([mock_metrics])

        # Should handle None values gracefully
        assert result["total_requests"] == 0
        assert result["avg_response_time"] == 0.0
        assert result["agent_count"] == 1


@pytest.mark.unit
class TestConfigurationMethods:
    """Test cases for configuration retrieval methods."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = MetricsService()

    @patch("src.arcp.services.metrics.config")
    def test_get_prometheus_config(self, mock_config):
        """Test Prometheus configuration retrieval."""
        mock_config.get_prometheus_config.return_value = {
            "enabled": True,
            "port": 9090,
            "path": "/metrics",
        }

        config_result = self.service.get_prometheus_config()

        assert config_result["enabled"] is True
        assert config_result["port"] == 9090
        assert config_result["path"] == "/metrics"
        mock_config.get_prometheus_config.assert_called_once()

    @patch("src.arcp.services.metrics.config")
    def test_get_grafana_config(self, mock_config):
        """Test Grafana configuration retrieval."""
        mock_config.get_grafana_config.return_value = {
            "url": "http://localhost:3000",
            "dashboard_id": "arcp-dashboard",
        }

        config_result = self.service.get_grafana_config()

        assert config_result["url"] == "http://localhost:3000"
        assert config_result["dashboard_id"] == "arcp-dashboard"
        mock_config.get_grafana_config.assert_called_once()


@pytest.mark.unit
class TestStatusReporting:
    """Test cases for metrics service status reporting."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = MetricsService()

    @patch("src.arcp.services.metrics.config")
    def test_get_status_complete(self, mock_config):
        """Test complete status reporting."""
        mock_config.get_prometheus_config.return_value = {"enabled": True}
        mock_config.get_grafana_config.return_value = {"enabled": True}

        self.service._prometheus_available = True
        self.service._psutil_available = True

        status = self.service.get_status()

        assert status["prometheus_available"] is True
        assert status["psutil_available"] is True
        assert "prometheus_config" in status
        assert "grafana_config" in status

    @patch("src.arcp.services.metrics.config")
    def test_get_status_minimal(self, mock_config):
        """Test status reporting with minimal availability."""
        mock_config.get_prometheus_config.return_value = {"enabled": False}
        mock_config.get_grafana_config.return_value = {"enabled": False}

        self.service._prometheus_available = False
        self.service._psutil_available = False

        status = self.service.get_status()

        assert status["prometheus_available"] is False
        assert status["psutil_available"] is False
        assert status["prometheus_config"]["enabled"] is False
        assert status["grafana_config"]["enabled"] is False


@pytest.mark.unit
class TestGlobalFunction:
    """Test cases for global convenience function."""

    @patch("src.arcp.services.metrics._metrics_service_instance")
    def test_get_metrics_service(self, mock_service):
        """Test get_metrics_service function."""
        result = get_metrics_service()

        assert result is mock_service


@pytest.mark.unit
class TestEdgeCasesAndErrorHandling:
    """Test cases for edge cases and error handling scenarios."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = MetricsService()

    def test_calculate_agent_metrics_summary_invalid_objects(self):
        """Test metrics summary with invalid metric objects."""
        invalid_objects = [
            None,
            "string",
            123,
            {"dict": "without methods"},
            MagicMock(spec=[]),  # Mock with no methods
        ]

        # Should not crash with invalid objects
        result = self.service.calculate_agent_metrics_summary(invalid_objects)

        assert isinstance(result, dict)
        assert result["agent_count"] == len(invalid_objects)
        assert result["total_requests"] >= 0
        assert result["avg_response_time"] >= 0.0
        assert result["error_rate"] >= 0.0

    @patch("src.arcp.services.metrics.PROMETHEUS_AVAILABLE", True)
    @patch("src.arcp.services.metrics.generate_latest")
    def test_get_prometheus_metrics_unicode_error(self, mock_generate):
        """Test Prometheus metrics with unicode encoding issues."""
        self.service._prometheus_available = True
        # Return bytes with potential unicode issues
        mock_generate.return_value = b"\xff\xfe# Invalid unicode"

        data, content_type = self.service.get_prometheus_metrics()

        # Should still return data without crashing
        assert isinstance(data, bytes)
        assert isinstance(content_type, str)

    @patch("src.arcp.services.metrics.PSUTIL_AVAILABLE", True)
    @patch("src.arcp.services.metrics.psutil")
    async def test_get_resource_utilization_partial_failure(self, mock_psutil):
        """Test resource utilization with partial failures."""
        self.service._psutil_available = True

        # Some operations succeed, others fail
        mock_psutil.cpu_percent.return_value = 25.0
        mock_psutil.virtual_memory.side_effect = Exception("Memory error")
        mock_psutil.net_io_counters.return_value = MagicMock(
            bytes_sent=1024, bytes_recv=2048
        )
        mock_psutil.disk_usage.side_effect = Exception("Disk error")

        metrics = await self.service.get_resource_utilization()

        # Should return actual values for successful operations, 0 for failed ones
        assert metrics["cpu"] == 25.0  # CPU succeeded
        assert metrics["memory"] == 0.0  # Memory failed
        assert metrics["network"] == 0.0  # Network will be 0 without previous data
        assert metrics["storage"] == 0.0  # Disk failed

    @patch("src.arcp.services.metrics.config")
    def test_config_methods_exception_handling(self, mock_config):
        """Test configuration methods handle exceptions gracefully."""
        mock_config.get_prometheus_config.side_effect = Exception("Config error")
        mock_config.get_grafana_config.side_effect = Exception("Config error")

        # Should not crash on config errors
        try:
            self.service.get_prometheus_config()
            self.service.get_grafana_config()
            self.service.get_status()
        except Exception as e:
            pytest.fail(
                f"Configuration methods should handle exceptions gracefully: {e}"
            )

    def test_calculate_agent_metrics_summary_extreme_values(self):
        """Test metrics summary with extreme values."""
        mock_metrics = MagicMock()
        mock_metrics.dict.return_value = {
            "total_requests": 100,  # Reasonable number
            "avg_response_time": 0.000001,  # Very small number
            "success_rate": 1.000000001,  # Invalid success rate (> 1)
        }

        result = self.service.calculate_agent_metrics_summary([mock_metrics])

        # Should handle extreme values gracefully
        assert result["total_requests"] == 100
        assert abs(result["avg_response_time"] - 0.000001) < 0.000002
        assert result["agent_count"] == 1
        # Error rate should be calculated correctly even with invalid success rate
        assert result["error_rate"] >= 0.0


@pytest.mark.unit
@pytest.mark.asyncio
class TestConcurrencyScenarios:
    """Test cases for concurrent operations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = MetricsService()

    @patch("src.arcp.services.metrics.PSUTIL_AVAILABLE", True)
    @patch("src.arcp.services.metrics.psutil")
    async def test_concurrent_resource_utilization_calls(self, mock_psutil):
        """Test concurrent resource utilization monitoring."""
        self.service._psutil_available = True

        # Mock psutil functions
        mock_psutil.cpu_percent.return_value = 50.0
        mock_psutil.virtual_memory.return_value = MagicMock(percent=60.0)
        mock_psutil.net_io_counters.return_value = MagicMock(
            bytes_sent=1024, bytes_recv=2048
        )
        mock_psutil.disk_usage.return_value = MagicMock(percent=70.0)

        # Mock disk_io_counters to avoid comparison errors
        mock_disk_io = MagicMock()
        mock_disk_io.read_bytes = 1024
        mock_disk_io.write_bytes = 2048
        mock_disk_io.read_count = 10
        mock_disk_io.write_count = 20
        mock_psutil.disk_io_counters.return_value = mock_disk_io

        # Execute multiple concurrent calls
        tasks = [self.service.get_resource_utilization() for _ in range(5)]
        results = await asyncio.gather(*tasks)

        # All should succeed and return consistent results
        for result in results:
            assert result["cpu"] == 50.0
            assert result["memory"] == 60.0
            assert (
                result["storage"] == 49.0
            )  # (70.0 * 0.7) + (0 * 0.3) = weighted calculation

    def test_concurrent_metrics_summary_calculation(self):
        """Test concurrent agent metrics summary calculations."""
        # Create mock metrics
        mock_metrics_list = []
        for i in range(10):
            mock_metrics = MagicMock()
            mock_metrics.dict.return_value = {
                "total_requests": 100 * (i + 1),
                "avg_response_time": 0.1 * (i + 1),
                "success_rate": 0.9 + (i * 0.01),
            }
            mock_metrics_list.append(mock_metrics)

        # Execute multiple concurrent calculations
        results = []
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(
                    self.service.calculate_agent_metrics_summary,
                    mock_metrics_list,
                )
                for _ in range(5)
            ]
            results = [future.result() for future in futures]

        # All should return the same result
        expected_total = sum(100 * (i + 1) for i in range(10))
        for result in results:
            assert result["total_requests"] == expected_total
            assert result["agent_count"] == 10


@pytest.mark.unit
class TestMetricsServiceIntegration:
    """Integration-style tests for MetricsService (still using mocks)."""

    @patch("src.arcp.services.metrics.PROMETHEUS_AVAILABLE", True)
    @patch("src.arcp.services.metrics.PSUTIL_AVAILABLE", True)
    @patch("src.arcp.services.metrics.generate_latest")
    @patch("src.arcp.services.metrics.psutil")
    @patch("src.arcp.services.metrics.config")
    def test_full_metrics_collection_cycle(
        self, mock_config, mock_psutil, mock_generate
    ):
        """Test full metrics collection cycle."""
        # Setup mocks
        mock_generate.return_value = b"prometheus_metrics_data"

        mock_psutil.cpu_percent.return_value = 45.0
        mock_psutil.virtual_memory.return_value = MagicMock(percent=67.0)
        mock_psutil.net_io_counters.return_value = MagicMock(
            bytes_sent=1024, bytes_recv=2048
        )
        mock_psutil.disk_usage.return_value = MagicMock(percent=82.0)

        mock_config.get_prometheus_config.return_value = {"enabled": True}
        mock_config.get_grafana_config.return_value = {"enabled": True}

        # Initialize service
        service = MetricsService()
        service._prometheus_available = True
        service._psutil_available = True

        # Test Prometheus metrics
        prom_data, prom_content_type = service.get_prometheus_metrics()
        assert b"prometheus_metrics_data" in prom_data

        # Test resource utilization
        async def test_resources():
            resources = await service.get_resource_utilization()
            assert resources["cpu"] == 45.0
            assert resources["memory"] == 67.0
            return resources

        import asyncio

        resources = asyncio.run(test_resources())

        # Test agent metrics summary
        mock_agent_metrics = [
            MagicMock(
                dict=lambda: {
                    "total_requests": 100,
                    "avg_response_time": 0.5,
                    "success_rate": 0.95,
                }
            ),
            MagicMock(
                dict=lambda: {
                    "total_requests": 200,
                    "avg_response_time": 0.3,
                    "success_rate": 0.98,
                }
            ),
        ]
        summary = service.calculate_agent_metrics_summary(mock_agent_metrics)
        assert summary["total_requests"] == 300
        assert summary["agent_count"] == 2

        # Test status
        status = service.get_status()
        assert status["prometheus_available"] is True
        assert status["psutil_available"] is True

        # Verify all components work together
        assert all([prom_data, resources, summary, status])
