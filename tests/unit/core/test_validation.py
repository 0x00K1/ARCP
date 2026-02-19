"""
Unit tests for TPR validation worker system.

Tests the async validation queue, worker lifecycle, and validation stages.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from arcp.core.validation import (
    create_security_binding,
    enqueue_validation,
    get_validation_queue,
    get_validation_result,
    perform_endpoint_validation,
    perform_fast_checks,
    start_validation_worker,
    stop_validation_workers,
    store_validation_result,
    validation_results,
    validation_worker,
    verify_capabilities,
)
from arcp.models.validation import SecurityBinding, ValidationRequest, ValidationResult


@pytest.fixture
async def clean_validation_state():
    """Clean validation queue and results before/after tests."""
    # Clear before test
    queue = get_validation_queue()
    while not queue.empty():
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            break

    validation_results.clear()

    yield

    # Clear after test
    queue = get_validation_queue()
    while not queue.empty():
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            break

    validation_results.clear()


@pytest.fixture
def mock_redis():
    """Mock Redis service."""
    with patch("arcp.core.validation.get_redis_service") as mock:
        mock_instance = AsyncMock()
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def validation_request():
    """Create a sample ValidationRequest."""
    return ValidationRequest(
        agent_id="test-agent-001",
        agent_type="test",
        endpoint="https://agent.example.com:8443",
        capabilities=["rag", "function_calling"],
    )


class TestValidationQueue:
    """Test validation queue operations."""

    @pytest.mark.asyncio
    async def test_enqueue_validation(self, clean_validation_state, validation_request):
        """Test enqueueing a validation request."""
        validation_id = await enqueue_validation(validation_request)

        assert validation_id is not None
        assert validation_id.startswith("val_")
        assert not get_validation_queue().empty()

    @pytest.mark.asyncio
    async def test_enqueue_validation_creates_pending_result(
        self, clean_validation_state, validation_request
    ):
        """Test enqueue creates pending result in memory."""
        validation_id = await enqueue_validation(validation_request)

        result = validation_results.get(validation_id)
        assert result is not None
        assert result.status == "pending"
        assert result.agent_id == "test-agent-001"

    @pytest.mark.asyncio
    async def test_enqueue_validation_queue_full(
        self, clean_validation_state, validation_request
    ):
        """Test enqueue when queue is full."""
        import arcp.core.validation as validation_module

        # Save original queue state
        original_queue = validation_module._validation_queue
        original_loop = validation_module._validation_queue_loop

        try:
            # Create a small queue and set it
            small_queue = asyncio.Queue(maxsize=1)
            validation_module._validation_queue = small_queue
            validation_module._validation_queue_loop = asyncio.get_running_loop()

            # Fill queue
            await enqueue_validation(validation_request)

            # Queue is full, next should raise
            with pytest.raises(asyncio.QueueFull):
                await enqueue_validation(validation_request)
        finally:
            # Restore original queue state
            validation_module._validation_queue = original_queue
            validation_module._validation_queue_loop = original_loop

    @pytest.mark.asyncio
    async def test_get_validation_result_from_memory(self, clean_validation_state):
        """Test getting validation result from in-memory cache."""
        result = ValidationResult(
            validation_id="val_test123",
            agent_id="test-agent-001",
            status="passed",
            validated_at=datetime.now(timezone.utc),
            security_binding=SecurityBinding(
                code_hash="sha256:abc123",
                endpoint_hash="sha256:def456",
            ),
        )

        validation_results["val_test123"] = result

        retrieved = await get_validation_result("val_test123")
        assert retrieved is not None
        assert retrieved.validation_id == "val_test123"
        assert retrieved.status == "passed"

    @pytest.mark.asyncio
    async def test_get_validation_result_from_redis(
        self, clean_validation_state, mock_redis
    ):
        """Test getting validation result returns None when not in memory."""
        # get_validation_result only checks in-memory dict, not Redis in current implementation
        retrieved = await get_validation_result("val_nonexistent")

        assert retrieved is None

    @pytest.mark.asyncio
    async def test_store_validation_result(self, clean_validation_state, mock_redis):
        """Test storing validation result in memory and Redis."""
        validation_id = "val_test123"
        result = ValidationResult(
            validation_id=validation_id,
            agent_id="test-agent-001",
            status="passed",
            binding=SecurityBinding(
                code_hash="sha256:abc123",
                endpoint_hash="sha256:def456",
            ),
            errors=[],
            warnings=[],
            endpoint_checks={},
            duration_ms=100,
        )

        await store_validation_result(validation_id, result)

        # Check in-memory storage
        assert validation_id in validation_results
        assert validation_results[validation_id].status == "passed"


class TestValidationStages:
    """Test individual validation stages."""

    @pytest.mark.asyncio
    async def test_perform_fast_checks_success(self, validation_request):
        """Test fast checks with valid agent."""
        result = ValidationResult(
            validation_id="val_test",
            agent_id="test-agent-001",
            status="pending",
            binding=None,
            errors=[],
            warnings=[],
            endpoint_checks={},
            duration_ms=0,
        )

        # Mock the httpx client to return successful health response
        with patch("arcp.core.validation.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "agent_id": "test-agent-001",
                "status": "healthy",
            }
            mock_client.get.return_value = mock_response

            await perform_fast_checks(validation_request, result)

            assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_perform_fast_checks_failure(self, validation_request):
        """Test fast checks with failing health endpoint."""
        result = ValidationResult(
            validation_id="val_test",
            agent_id="test-agent-001",
            status="pending",
            binding=None,
            errors=[],
            warnings=[],
            endpoint_checks={},
            duration_ms=0,
        )

        # Mock the httpx client to return failed health response
        with patch("arcp.core.validation.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 503
            mock_client.get.return_value = mock_response

            await perform_fast_checks(validation_request, result)

            assert len(result.errors) > 0
            assert any(
                "health" in str(e.get("type", "")).lower()
                or "health" in str(e.get("message", "")).lower()
                for e in result.errors
            )

    @pytest.mark.asyncio
    async def test_perform_endpoint_validation_success(self, validation_request):
        """Test full endpoint validation."""
        with patch("arcp.core.validation.validate_agent_endpoints") as mock_validate:
            from arcp.utils.endpoint_validator import EndpointValidationResult

            mock_result = EndpointValidationResult("test-agent-001")
            mock_validate.return_value = mock_result

            result = ValidationResult(
                validation_id="val_test",
                agent_id="test-agent-001",
                status="pending",
                binding=None,
                errors=[],
                warnings=[],
                endpoint_checks={},
                duration_ms=0,
            )

            await perform_endpoint_validation(validation_request, result)

            assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_verify_capabilities(self, validation_request):
        """Test capability verification."""
        result = ValidationResult(
            validation_id="val_test",
            agent_id="test-agent-001",
            status="pending",
            binding=None,
            errors=[],
            warnings=[],
            endpoint_checks={},
            duration_ms=0,
        )

        await verify_capabilities(validation_request, result)

        # Should not produce warnings for valid capabilities
        assert len(result.warnings) == 0

    @pytest.mark.asyncio
    async def test_create_security_binding(self, validation_request):
        """Test security binding creation."""
        result = ValidationResult(
            validation_id="val_test",
            agent_id="test-agent-001",
            status="pending",
            binding=None,
            errors=[],
            warnings=[],
            endpoint_checks={},
            duration_ms=0,
        )

        binding = create_security_binding(validation_request, result)

        assert binding is not None
        assert binding.code_hash is not None
        assert binding.endpoint_hash is not None


class TestValidationWorker:
    """Test validation worker logic."""

    @pytest.mark.asyncio
    async def test_validation_worker_processes_request(
        self, clean_validation_state, validation_request
    ):
        """Test worker processes validation request."""
        with (
            patch("arcp.core.validation.httpx.AsyncClient") as mock_client_class,
            patch("arcp.core.validation.config.ENDPOINT_VALIDATION_ENABLED", False),
            patch("arcp.core.validation.get_redis_service") as mock_redis,
        ):

            # Mock successful health check
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "agent_id": "test-agent-001",
                "status": "healthy",
            }
            mock_client.get.return_value = mock_response

            # Mock Redis as unavailable
            mock_redis.return_value = None

            # Enqueue request
            validation_id = await enqueue_validation(validation_request)

            # Run worker once with timeout
            worker_task = asyncio.create_task(validation_worker())

            # Wait for queue to be processed
            queue = get_validation_queue()
            try:
                await asyncio.wait_for(queue.join(), timeout=2.0)
            except asyncio.TimeoutError:
                pass

            # Cancel worker
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass

            # Check result was updated
            result = validation_results.get(validation_id)
            assert result is not None
            assert result.status == "passed"

    @pytest.mark.asyncio
    async def test_validation_worker_handles_failure(
        self, clean_validation_state, validation_request
    ):
        """Test worker handles validation failure."""
        with (
            patch("arcp.core.validation.httpx.AsyncClient") as mock_client_class,
            patch("arcp.core.validation.get_redis_service") as mock_redis,
        ):

            # Mock failed health check (timeout)
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            import httpx

            mock_client.get.side_effect = httpx.TimeoutException("Timeout")

            # Mock Redis as unavailable
            mock_redis.return_value = None

            # Enqueue request
            validation_id = await enqueue_validation(validation_request)

            # Run worker once with timeout
            worker_task = asyncio.create_task(validation_worker())

            # Wait for queue to be processed
            queue = get_validation_queue()
            try:
                await asyncio.wait_for(queue.join(), timeout=2.0)
            except asyncio.TimeoutError:
                pass

            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass

            # Check failure was stored
            result = validation_results.get(validation_id)
            assert result is not None
            assert result.status == "failed"


class TestWorkerLifecycle:
    """Test worker lifecycle management."""

    @pytest.mark.asyncio
    async def test_start_validation_worker(self, clean_validation_state):
        """Test starting validation workers."""
        from arcp.core import validation as validation_module

        # Save original worker tasks
        original_tasks = validation_module._worker_tasks.copy()
        validation_module._worker_tasks.clear()

        try:
            with (
                patch.object(validation_module.config, "FEATURE_THREE_PHASE", True),
                patch.object(validation_module.config, "VALIDATION_WORKER_COUNT", 2),
            ):
                start_validation_worker()

                assert len(validation_module._worker_tasks) == 2

                # Cleanup
                stop_validation_workers()

                # Give workers time to cancel
                await asyncio.sleep(0.1)
        finally:
            # Restore original state
            validation_module._worker_tasks = original_tasks

    @pytest.mark.asyncio
    async def test_stop_validation_workers(self, clean_validation_state):
        """Test stopping validation workers."""
        from arcp.core import validation as validation_module

        # Save original worker tasks
        original_tasks = validation_module._worker_tasks.copy()
        validation_module._worker_tasks.clear()

        try:
            with (
                patch.object(validation_module.config, "FEATURE_THREE_PHASE", True),
                patch.object(validation_module.config, "VALIDATION_WORKER_COUNT", 2),
            ):
                start_validation_worker()
                tasks_before_stop = validation_module._worker_tasks.copy()
                assert len(tasks_before_stop) == 2

                stop_validation_workers()

                # Give workers time to cancel
                await asyncio.sleep(0.1)

                # Workers should be cancelled
                for worker in tasks_before_stop:
                    assert worker.cancelled() or worker.done()
        finally:
            # Restore original state
            validation_module._worker_tasks = original_tasks

    @pytest.mark.asyncio
    async def test_worker_restarts_on_error(
        self, clean_validation_state, validation_request
    ):
        """Test worker continues after processing error."""
        call_count = 0

        async def mock_fast_checks(request, result):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Test error")
            # Second call succeeds (adds no errors)

        with (
            patch("arcp.core.validation.httpx.AsyncClient"),
            patch("arcp.core.validation.get_redis_service") as mock_redis,
        ):

            # Mock Redis as unavailable
            mock_redis.return_value = None

            # Start worker
            worker_task = asyncio.create_task(validation_worker())

            # Give worker time to start
            await asyncio.sleep(0.05)

            # Enqueue first request (will fail with exception)
            with patch(
                "arcp.core.validation.perform_fast_checks", side_effect=mock_fast_checks
            ):
                await enqueue_validation(validation_request)

                # Wait for first item to be processed
                queue = get_validation_queue()
                try:
                    await asyncio.wait_for(queue.join(), timeout=2.0)
                except asyncio.TimeoutError:
                    pass

            # Worker should still be running after exception
            assert not worker_task.done()

            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
