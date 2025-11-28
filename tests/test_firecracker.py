"""Tests for Phase 20.1 - Firecracker Sandboxing"""

import pytest
import time
from src.sandbox.firecracker import (
    FirecrackerVM,
    ResourceLimits,
    VMState,
    SandboxError,
    SandboxedExecutor,
)


@pytest.fixture
def firecracker():
    """Create a Firecracker VM manager in mock mode."""
    return FirecrackerVM(mock_mode=True)


@pytest.fixture
def executor():
    """Create a sandboxed executor in mock mode."""
    return SandboxedExecutor(
        default_image="/mock/rootfs.img",
        mock_mode=True
    )


class TestResourceLimits:
    """Test ResourceLimits validation."""
    
    def test_valid_limits(self):
        """Test creating valid resource limits."""
        limits = ResourceLimits(
            cpu_cores=2,
            mem_mb=512,
            disk_mb=2048,
            net_bw_mbps=100
        )
        limits.validate()  # Should not raise
    
    def test_default_limits(self):
        """Test default resource limits."""
        limits = ResourceLimits()
        assert limits.cpu_cores == 1
        assert limits.mem_mb == 128
        assert limits.disk_mb == 1024
        assert limits.net_bw_mbps == 100
        limits.validate()
    
    def test_invalid_cpu_cores(self):
        """Test that invalid CPU cores are rejected."""
        limits = ResourceLimits(cpu_cores=0)
        with pytest.raises(ValueError, match="cpu_cores must be between"):
            limits.validate()
        
        limits = ResourceLimits(cpu_cores=50)
        with pytest.raises(ValueError, match="cpu_cores must be between"):
            limits.validate()
    
    def test_invalid_memory(self):
        """Test that invalid memory is rejected."""
        limits = ResourceLimits(mem_mb=32)
        with pytest.raises(ValueError, match="mem_mb must be between"):
            limits.validate()
        
        limits = ResourceLimits(mem_mb=99999)
        with pytest.raises(ValueError, match="mem_mb must be between"):
            limits.validate()
    
    def test_invalid_disk(self):
        """Test that invalid disk size is rejected."""
        limits = ResourceLimits(disk_mb=50)
        with pytest.raises(ValueError, match="disk_mb must be between"):
            limits.validate()
    
    def test_invalid_network(self):
        """Test that invalid network bandwidth is rejected."""
        limits = ResourceLimits(net_bw_mbps=0)
        with pytest.raises(ValueError, match="net_bw_mbps must be between"):
            limits.validate()


class TestFirecrackerVM:
    """Test FirecrackerVM functionality."""
    
    def test_initialization_mock_mode(self):
        """Test initializing in mock mode."""
        fc = FirecrackerVM(mock_mode=True)
        assert fc.mock_mode is True
        assert len(fc.vms) == 0
    
    def test_start_vm(self, firecracker):
        """Test starting a VM."""
        vm_id = firecracker.start_vm("/mock/image.img")
        
        assert vm_id is not None
        assert vm_id in firecracker.vms
        
        vm_info = firecracker.get_vm_info(vm_id)
        assert vm_info.state == VMState.RUNNING
        assert vm_info.image == "/mock/image.img"
    
    def test_start_vm_with_custom_resources(self, firecracker):
        """Test starting VM with custom resource limits."""
        limits = ResourceLimits(
            cpu_cores=4,
            mem_mb=1024,
            disk_mb=4096,
            net_bw_mbps=500
        )
        
        vm_id = firecracker.start_vm("/mock/image.img", limits)
        
        vm_info = firecracker.get_vm_info(vm_id)
        assert vm_info.resources.cpu_cores == 4
        assert vm_info.resources.mem_mb == 1024
    
    def test_start_vm_invalid_resources(self, firecracker):
        """Test that invalid resources are rejected."""
        limits = ResourceLimits(cpu_cores=0)  # Invalid
        
        with pytest.raises(ValueError):
            firecracker.start_vm("/mock/image.img", limits)
    
    def test_exec_in_vm(self, firecracker):
        """Test executing command in VM."""
        vm_id = firecracker.start_vm("/mock/image.img")
        
        result = firecracker.exec_in_vm(vm_id, "echo Hello World")
        
        assert result["exit_code"] == 0
        assert "Hello World" in result["stdout"]
        assert result["stderr"] == ""
        assert result["execution_time"] >= 0
    
    def test_exec_in_vm_error_command(self, firecracker):
        """Test executing command that returns error."""
        vm_id = firecracker.start_vm("/mock/image.img")
        
        result = firecracker.exec_in_vm(vm_id, "error command")
        
        assert result["exit_code"] == 1
        assert result["stderr"] != ""
    
    def test_exec_in_nonexistent_vm(self, firecracker):
        """Test that executing in non-existent VM fails."""
        with pytest.raises(SandboxError, match="does not exist"):
            firecracker.exec_in_vm("fake-vm-id", "echo test")
    
    def test_exec_in_stopped_vm(self, firecracker):
        """Test that executing in stopped VM fails."""
        vm_id = firecracker.start_vm("/mock/image.img")
        firecracker.stop_vm(vm_id)
        
        with pytest.raises(SandboxError, match="does not exist"):
            firecracker.exec_in_vm(vm_id, "echo test")
    
    def test_stop_vm(self, firecracker):
        """Test stopping a VM."""
        vm_id = firecracker.start_vm("/mock/image.img")
        assert vm_id in firecracker.vms
        
        firecracker.stop_vm(vm_id)
        assert vm_id not in firecracker.vms
    
    def test_stop_nonexistent_vm(self, firecracker):
        """Test that stopping non-existent VM fails."""
        with pytest.raises(SandboxError, match="does not exist"):
            firecracker.stop_vm("fake-vm-id")
    
    def test_list_vms(self, firecracker):
        """Test listing all VMs."""
        assert len(firecracker.list_vms()) == 0
        
        vm1 = firecracker.start_vm("/mock/image1.img")
        vm2 = firecracker.start_vm("/mock/image2.img")
        
        vms = firecracker.list_vms()
        assert len(vms) == 2
        assert any(vm.vm_id == vm1 for vm in vms)
        assert any(vm.vm_id == vm2 for vm in vms)
    
    def test_cleanup_all(self, firecracker):
        """Test cleaning up all VMs."""
        firecracker.start_vm("/mock/image1.img")
        firecracker.start_vm("/mock/image2.img")
        firecracker.start_vm("/mock/image3.img")
        
        assert len(firecracker.list_vms()) == 3
        
        firecracker.cleanup_all()
        assert len(firecracker.list_vms()) == 0
    
    def test_multiple_vms_independent(self, firecracker):
        """Test that multiple VMs operate independently."""
        vm1 = firecracker.start_vm("/mock/image1.img")
        vm2 = firecracker.start_vm("/mock/image2.img")
        
        # Execute in both
        result1 = firecracker.exec_in_vm(vm1, "echo VM1")
        result2 = firecracker.exec_in_vm(vm2, "echo VM2")
        
        assert "VM1" in result1["stdout"]
        assert "VM2" in result2["stdout"]
        
        # Stop one shouldn't affect the other
        firecracker.stop_vm(vm1)
        
        result2 = firecracker.exec_in_vm(vm2, "echo Still running")
        assert result2["exit_code"] == 0


class TestSandboxedExecutor:
    """Test SandboxedExecutor high-level API."""
    
    def test_execute_sandboxed(self, executor):
        """Test executing command in sandbox."""
        result = executor.execute_sandboxed("echo Hello Sandbox")
        
        assert result["exit_code"] == 0
        assert "Hello Sandbox" in result["stdout"]
        assert result["stderr"] == ""
    
    def test_execute_sandboxed_with_resources(self, executor):
        """Test executing with custom resource limits."""
        limits = ResourceLimits(
            cpu_cores=2,
            mem_mb=512
        )
        
        result = executor.execute_sandboxed(
            "echo Test",
            resources=limits
        )
        
        assert result["exit_code"] == 0
    
    def test_execute_sandboxed_timeout(self, executor):
        """Test execution with timeout."""
        result = executor.execute_sandboxed(
            "echo Quick",
            timeout=5
        )
        
        assert result["exit_code"] == 0
        assert result["execution_time"] < 5
    
    def test_execute_sandboxed_cleans_up(self, executor):
        """Test that VM is cleaned up after execution."""
        # Execute should create and destroy VM
        result = executor.execute_sandboxed("echo Test")
        
        # No VMs should remain
        assert len(executor.firecracker.list_vms()) == 0
    
    def test_execute_sandboxed_error_cleanup(self, executor):
        """Test that VM is cleaned up even on error."""
        # Force an error by using invalid command
        result = executor.execute_sandboxed("error command")
        
        # VM should still be cleaned up
        assert len(executor.firecracker.list_vms()) == 0
    
    def test_cleanup(self, executor):
        """Test manual cleanup."""
        executor.cleanup()
        assert len(executor.firecracker.list_vms()) == 0


class TestIsolation:
    """Test isolation properties of sandboxing."""
    
    def test_resource_isolation(self, firecracker):
        """Test that VMs have independent resources."""
        limits1 = ResourceLimits(cpu_cores=1, mem_mb=128)
        limits2 = ResourceLimits(cpu_cores=4, mem_mb=2048)
        
        vm1 = firecracker.start_vm("/mock/image.img", limits1)
        vm2 = firecracker.start_vm("/mock/image.img", limits2)
        
        info1 = firecracker.get_vm_info(vm1)
        info2 = firecracker.get_vm_info(vm2)
        
        assert info1.resources.cpu_cores == 1
        assert info2.resources.cpu_cores == 4
        assert info1.resources.mem_mb == 128
        assert info2.resources.mem_mb == 2048
    
    def test_execution_isolation(self, executor):
        """Test that executions are isolated."""
        # Execute multiple commands
        results = []
        for i in range(3):
            result = executor.execute_sandboxed(f"echo Task {i}")
            results.append(result)
        
        # All should succeed independently
        assert all(r["exit_code"] == 0 for r in results)
        assert "Task 0" in results[0]["stdout"]
        assert "Task 1" in results[1]["stdout"]
        assert "Task 2" in results[2]["stdout"]


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_empty_command(self, firecracker):
        """Test executing empty command."""
        vm_id = firecracker.start_vm("/mock/image.img")
        result = firecracker.exec_in_vm(vm_id, "")
        
        # Should still return valid result
        assert "exit_code" in result
    
    def test_very_long_command(self, executor):
        """Test executing very long command."""
        long_cmd = "echo " + "A" * 1000
        result = executor.execute_sandboxed(long_cmd)
        
        assert result["exit_code"] == 0
    
    def test_minimal_resources(self):
        """Test VM with minimal resources."""
        limits = ResourceLimits(
            cpu_cores=1,
            mem_mb=64,
            disk_mb=100,
            net_bw_mbps=1
        )
        
        fc = FirecrackerVM(mock_mode=True)
        vm_id = fc.start_vm("/mock/image.img", limits)
        
        result = fc.exec_in_vm(vm_id, "echo Minimal")
        assert result["exit_code"] == 0
    
    def test_maximal_resources(self):
        """Test VM with maximal resources."""
        limits = ResourceLimits(
            cpu_cores=32,
            mem_mb=32768,
            disk_mb=102400,
            net_bw_mbps=10000
        )
        
        fc = FirecrackerVM(mock_mode=True)
        vm_id = fc.start_vm("/mock/image.img", limits)
        
        result = fc.exec_in_vm(vm_id, "echo Maximal")
        assert result["exit_code"] == 0


class TestMockMode:
    """Test mock mode behavior."""
    
    def test_mock_mode_auto_detect_non_linux(self):
        """Test that mock mode is auto-enabled on non-Linux."""
        fc = FirecrackerVM(mock_mode=None)  # Auto-detect
        
        # On macOS (current platform), should be mock mode
        assert fc.mock_mode is True
    
    def test_explicit_mock_mode(self):
        """Test explicitly enabling mock mode."""
        fc = FirecrackerVM(mock_mode=True)
        assert fc.mock_mode is True
        
        # Should work fine
        vm_id = fc.start_vm("/mock/image.img")
        result = fc.exec_in_vm(vm_id, "echo test")
        assert result["exit_code"] == 0
    
    def test_mock_exec_behavior(self, firecracker):
        """Test mock execution behavior."""
        vm_id = firecracker.start_vm("/mock/image.img")
        
        # Echo command
        result = firecracker.exec_in_vm(vm_id, "echo Hello")
        assert "Hello" in result["stdout"]
        assert result["exit_code"] == 0
        
        # Error command
        result = firecracker.exec_in_vm(vm_id, "error test")
        assert result["exit_code"] == 1
        assert result["stderr"] != ""
        
        # Generic command
        result = firecracker.exec_in_vm(vm_id, "ls -la")
        assert result["exit_code"] == 0
        assert "Mock execution" in result["stdout"]
