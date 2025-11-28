"""Phase 20.1 - Firecracker MicroVM Sandboxing

This module implements secure execution isolation using Firecracker microVMs.

IMPORTANT: Firecracker requires Linux with KVM support. This implementation includes
a mock mode for cross-platform development and testing. For production deployment,
ensure you're running on a Linux host with KVM enabled.

Architecture:
- FirecrackerVM: Manages individual microVM instances
- ResourceLimits: Defines resource constraints for VMs
- Mock mode: Simulates VM behavior for development on non-Linux systems
"""

from dataclasses import dataclass
from typing import Dict, Optional, List
from enum import Enum
import subprocess
import uuid
import json
import os
import sys
import time


class VMState(Enum):
    """State of a Firecracker VM."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class SandboxError(Exception):
    """Base exception for sandbox-related errors."""
    pass


@dataclass
class ResourceLimits:
    """Resource limits for a Firecracker VM."""
    cpu_cores: int = 1
    mem_mb: int = 128
    disk_mb: int = 1024
    net_bw_mbps: int = 100  # Network bandwidth in Mbps
    
    def validate(self):
        """Validate resource limits."""
        if self.cpu_cores < 1 or self.cpu_cores > 32:
            raise ValueError("cpu_cores must be between 1 and 32")
        if self.mem_mb < 64 or self.mem_mb > 32768:
            raise ValueError("mem_mb must be between 64 and 32768")
        if self.disk_mb < 100 or self.disk_mb > 102400:
            raise ValueError("disk_mb must be between 100 and 102400")
        if self.net_bw_mbps < 1 or self.net_bw_mbps > 10000:
            raise ValueError("net_bw_mbps must be between 1 and 10000")


@dataclass
class VMInfo:
    """Information about a running VM."""
    vm_id: str
    state: VMState
    resources: ResourceLimits
    image: str
    created_at: float
    pid: Optional[int] = None


class FirecrackerVM:
    """
    Manages Firecracker microVM instances for secure code execution.
    
    This class provides an abstraction layer over Firecracker that can run
    in either real mode (on Linux with KVM) or mock mode (for development).
    """
    
    def __init__(self, mock_mode: Optional[bool] = None):
        """
        Initialize Firecracker VM manager.
        
        Args:
            mock_mode: If True, use mock implementation. If None, auto-detect
                      based on platform (True on non-Linux, False on Linux with KVM)
        """
        if mock_mode is None:
            # Auto-detect: use mock mode on non-Linux systems
            self.mock_mode = not self._is_firecracker_available()
        else:
            self.mock_mode = mock_mode
        
        self.vms: Dict[str, VMInfo] = {}
        
        if not self.mock_mode and not self._is_firecracker_available():
            raise SandboxError(
                "Firecracker is not available. Either install Firecracker on Linux "
                "with KVM support, or enable mock_mode for development."
            )
    
    def _is_firecracker_available(self) -> bool:
        """Check if Firecracker is available on this system."""
        # Check if on Linux
        if sys.platform != "linux":
            return False
        
        # Check if firecracker binary exists
        try:
            result = subprocess.run(
                ["which", "firecracker"],
                capture_output=True,
                timeout=5
            )
            if result.returncode != 0:
                return False
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
        
        # Check if KVM is available
        if not os.path.exists("/dev/kvm"):
            return False
        
        return True
    
    def start_vm(
        self, 
        image: str, 
        resources: Optional[ResourceLimits] = None
    ) -> str:
        """
        Start a new Firecracker microVM.
        
        Args:
            image: Path to the root filesystem image
            resources: Resource limits for the VM (uses defaults if None)
        
        Returns:
            vm_id: Unique identifier for the VM
        
        Raises:
            SandboxError: If VM fails to start
        """
        if resources is None:
            resources = ResourceLimits()
        
        resources.validate()
        
        vm_id = str(uuid.uuid4())
        
        if self.mock_mode:
            # Mock implementation
            vm_info = VMInfo(
                vm_id=vm_id,
                state=VMState.RUNNING,
                resources=resources,
                image=image,
                created_at=time.time(),
                pid=None  # No real process in mock mode
            )
            self.vms[vm_id] = vm_info
            return vm_id
        else:
            # Real Firecracker implementation
            return self._start_firecracker_vm(vm_id, image, resources)
    
    def _start_firecracker_vm(
        self, 
        vm_id: str, 
        image: str, 
        resources: ResourceLimits
    ) -> str:
        """
        Start a real Firecracker VM (Linux only).
        
        This is a simplified implementation. Production usage would require:
        - Proper network configuration
        - Boot source configuration
        - API socket setup
        - Proper error handling
        """
        # Create Firecracker configuration
        config = {
            "boot-source": {
                "kernel_image_path": "/path/to/vmlinux",  # Placeholder
                "boot_args": "console=ttyS0 reboot=k panic=1"
            },
            "drives": [{
                "drive_id": "rootfs",
                "path_on_host": image,
                "is_root_device": True,
                "is_read_only": False
            }],
            "machine-config": {
                "vcpu_count": resources.cpu_cores,
                "mem_size_mib": resources.mem_mb
            }
        }
        
        # In production, this would:
        # 1. Create a Unix socket for Firecracker API
        # 2. Start firecracker process
        # 3. Send configuration via API
        # 4. Start the VM
        
        vm_info = VMInfo(
            vm_id=vm_id,
            state=VMState.RUNNING,
            resources=resources,
            image=image,
            created_at=time.time(),
            pid=None  # Would be real PID in production
        )
        self.vms[vm_id] = vm_info
        
        return vm_id
    
    def exec_in_vm(self, vm_id: str, command: str, timeout: int = 30) -> Dict:
        """
        Execute a command inside a VM.
        
        Args:
            vm_id: ID of the VM
            command: Command to execute
            timeout: Timeout in seconds
        
        Returns:
            Dictionary with:
            - stdout: Standard output
            - stderr: Standard error
            - exit_code: Exit code
            - execution_time: Time taken in seconds
        
        Raises:
            SandboxError: If VM doesn't exist or execution fails
        """
        if vm_id not in self.vms:
            raise SandboxError(f"VM {vm_id} does not exist")
        
        vm_info = self.vms[vm_id]
        
        if vm_info.state != VMState.RUNNING:
            raise SandboxError(f"VM {vm_id} is not running (state: {vm_info.state})")
        
        if self.mock_mode:
            # Mock implementation - simulate command execution
            return self._mock_exec(command, timeout)
        else:
            # Real implementation would use Firecracker API or SSH
            return self._real_exec(vm_id, command, timeout)
    
    def _mock_exec(self, command: str, timeout: int) -> Dict:
        """Mock command execution for development."""
        start_time = time.time()
        
        # Simulate some execution time
        exec_time = min(0.1, timeout)
        time.sleep(exec_time)
        
        # Simple mock responses based on command
        if "error" in command.lower():
            return {
                "stdout": "",
                "stderr": "Mock error occurred",
                "exit_code": 1,
                "execution_time": exec_time
            }
        elif "echo" in command.lower():
            # Extract echo content
            parts = command.split("echo", 1)
            output = parts[1].strip() if len(parts) > 1 else ""
            return {
                "stdout": output + "\n",
                "stderr": "",
                "exit_code": 0,
                "execution_time": exec_time
            }
        else:
            return {
                "stdout": f"Mock execution of: {command}\n",
                "stderr": "",
                "exit_code": 0,
                "execution_time": exec_time
            }
    
    def _real_exec(self, vm_id: str, command: str, timeout: int) -> Dict:
        """Execute command in real Firecracker VM."""
        # In production, this would:
        # 1. Use vsock or SSH to connect to VM
        # 2. Execute command
        # 3. Capture output
        # 4. Return results
        
        # Placeholder for real implementation
        raise NotImplementedError(
            "Real Firecracker execution requires full setup. "
            "Use mock_mode=True for development."
        )
    
    def stop_vm(self, vm_id: str):
        """
        Stop and remove a VM.
        
        Args:
            vm_id: ID of the VM to stop
        
        Raises:
            SandboxError: If VM doesn't exist
        """
        if vm_id not in self.vms:
            raise SandboxError(f"VM {vm_id} does not exist")
        
        vm_info = self.vms[vm_id]
        
        if self.mock_mode:
            # Mock implementation - just remove from tracking
            vm_info.state = VMState.STOPPED
            del self.vms[vm_id]
        else:
            # Real implementation - stop Firecracker process
            self._stop_firecracker_vm(vm_id)
            del self.vms[vm_id]
    
    def _stop_firecracker_vm(self, vm_id: str):
        """Stop a real Firecracker VM."""
        vm_info = self.vms[vm_id]
        
        # In production, this would:
        # 1. Send shutdown command via API
        # 2. Wait for graceful shutdown
        # 3. Force kill if necessary
        # 4. Clean up resources
        
        vm_info.state = VMState.STOPPED
    
    def get_vm_info(self, vm_id: str) -> Optional[VMInfo]:
        """Get information about a VM."""
        return self.vms.get(vm_id)
    
    def list_vms(self) -> List[VMInfo]:
        """List all running VMs."""
        return list(self.vms.values())
    
    def cleanup_all(self):
        """Stop and clean up all VMs."""
        vm_ids = list(self.vms.keys())
        for vm_id in vm_ids:
            try:
                self.stop_vm(vm_id)
            except SandboxError:
                pass  # VM might already be stopped


class SandboxedExecutor:
    """
    High-level interface for executing untrusted code in sandboxed VMs.
    
    This provides a simpler API for common use cases.
    """
    
    def __init__(self, default_image: str, mock_mode: Optional[bool] = None):
        """
        Initialize sandboxed executor.
        
        Args:
            default_image: Default VM image to use
            mock_mode: Whether to use mock mode (auto-detect if None)
        """
        self.firecracker = FirecrackerVM(mock_mode=mock_mode)
        self.default_image = default_image
    
    def execute_sandboxed(
        self,
        command: str,
        resources: Optional[ResourceLimits] = None,
        timeout: int = 30
    ) -> Dict:
        """
        Execute a command in a fresh sandboxed VM.
        
        Creates a new VM, executes the command, and cleans up.
        
        Args:
            command: Command to execute
            resources: Resource limits (uses defaults if None)
            timeout: Execution timeout in seconds
        
        Returns:
            Execution results (stdout, stderr, exit_code, execution_time)
        """
        vm_id = None
        try:
            # Start VM
            vm_id = self.firecracker.start_vm(self.default_image, resources)
            
            # Execute command
            result = self.firecracker.exec_in_vm(vm_id, command, timeout)
            
            return result
        finally:
            # Always clean up VM
            if vm_id:
                try:
                    self.firecracker.stop_vm(vm_id)
                except SandboxError:
                    pass
    
    def cleanup(self):
        """Clean up all VMs."""
        self.firecracker.cleanup_all()
