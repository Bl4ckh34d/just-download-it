import multiprocessing as mp
from typing import Any, Callable, Optional, Dict
import uuid
import time

from utils.logger import Logger
from utils.exceptions import ProcessError

logger = Logger.get_logger(__name__)

class ProcessPool:
    """Pool for managing background processes"""
    
    def __init__(self, max_processes: int = 4):
        """Initialize process pool"""
        self.max_processes = max_processes
        self.processes: Dict[str, mp.Process] = {}
        self.cancel_events: Dict[str, mp.Event] = {}
        self.results = {}
        self.errors = {}
        logger.debug(f"Process pool initialized with max_processes={max_processes}")
        
    def start_process(self, target: Callable, args: tuple = ()) -> str:
        """Start a new process and return its ID"""
        try:
            # Check if we can start a new process
            active = len([p for p in self.processes.values() if p.is_alive()])
            if active >= self.max_processes:
                raise ProcessError(f"Maximum number of processes ({self.max_processes}) reached")
            
            process_id = str(uuid.uuid4())
            
            # Create cancel event
            cancel_event = mp.Event()
            self.cancel_events[process_id] = cancel_event
            
            # Add cancel event to args
            args = (*args, cancel_event)
            
            # Create and start process
            process = mp.Process(target=target, args=args)
            process.start()
            
            # Store process
            self.processes[process_id] = process
            logger.debug(f"Started process {process_id}")
            
            return process_id
            
        except Exception as e:
            logger.error(f"Failed to start process: {str(e)}", exc_info=True)
            raise ProcessError(str(e))
            
    def _run_process(self, process_id: str, target: Callable, args: tuple):
        """Run the target function and store its result"""
        try:
            result = target(*args)
            self.results[process_id] = result
        except Exception as e:
            self.errors[process_id] = str(e)
            logger.error(f"Process {process_id} failed: {str(e)}", exc_info=True)
            raise ProcessError(str(e))
            
    def get_process_status(self, process_id: str) -> str:
        """Get the status of a process"""
        if process_id not in self.processes:
            return "not_found"
            
        process = self.processes[process_id]
        
        if process_id in self.errors:
            return "failed"
            
        if not process.is_alive():
            if process_id in self.results:
                return "completed"
            else:
                return "cancelled"
                
        return "running"
        
    def get_process_error(self, process_id: str) -> Optional[str]:
        """Get the error message if process failed"""
        return self.errors.get(process_id)
        
    def get_process_result(self, process_id: str) -> Any:
        """Get the result of a completed process"""
        return self.results.get(process_id)
        
    def terminate_process(self, process_id: str):
        """Terminate a running process"""
        if process_id in self.processes:
            # Set cancel event
            if process_id in self.cancel_events:
                self.cancel_events[process_id].set()
                
            # Wait a bit for graceful shutdown
            time.sleep(0.5)
            
            # Force terminate if still running
            process = self.processes[process_id]
            if process.is_alive():
                process.terminate()
                process.join()
                
            # Clean up
            if process_id in self.cancel_events:
                del self.cancel_events[process_id]
                
            logger.debug(f"Terminated process {process_id}")
            
    def cleanup(self):
        """Terminate all processes and cleanup"""
        for process_id in list(self.processes.keys()):
            self.terminate_process(process_id)
        self.processes.clear()
        self.cancel_events.clear()
        self.results.clear()
        self.errors.clear()
        logger.debug("Process pool cleaned up")
        
    def cleanup_completed(self):
        """Remove completed processes from the pool"""
        for process_id in list(self.processes.keys()):
            if not self.processes[process_id].is_alive():
                self.processes.pop(process_id)
                logger.debug(f"Removed completed process {process_id}")

    def is_process_running(self, process_id: str) -> bool:
        """Check if a process is still running"""
        if process_id not in self.processes:
            return False
        return self.processes[process_id].is_alive()
