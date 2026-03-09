"""
Performance timing and profiling utilities
"""

import time
from typing import Optional, Dict, List
from contextlib import contextmanager

class TimingTracker:
    """Track timing of different components throughout request"""
    
    def __init__(self):
        self.timings: Dict[str, List[float]] = {}
        self.start_time = time.time()
        self.last_checkpoint_time = self.start_time
        self.checkpoints: List[tuple] = []
    
    def checkpoint(self, name: str):
        """Record a checkpoint"""
        now = time.time()
        elapsed_since_last = (now - self.last_checkpoint_time) * 1000  # Convert to ms
        total_elapsed = (now - self.start_time) * 1000
        
        self.checkpoints.append((name, elapsed_since_last, total_elapsed))
        self.last_checkpoint_time = now
        
        # Print checkpoint
        print(f"[TIMING] ⏱️  {name}: {elapsed_since_last:.0f}ms (total: {total_elapsed:.0f}ms)")
    
    def get_report(self) -> str:
        """Generate a timing report"""
        total = (time.time() - self.start_time) * 1000
        
        report = "\n" + "="*60
        report += "\n[TIMING] 📊 PERFORMANCE REPORT\n"
        report += "="*60 + "\n"
        
        prev_total = 0
        for name, delta, cumulative in self.checkpoints:
            bar_length = int(delta / 5)
            bar = "█" * min(bar_length, 50)
            report += f"{name:.<40} {delta:>6.0f}ms {bar}\n"
            prev_total = cumulative
        
        report += "-"*60 + "\n"
        report += f"{'TOTAL':.<40} {total:>6.0f}ms\n"
        report += "="*60 + "\n"
        
        return report
    
    def print_report(self):
        """Print the timing report"""
        print(self.get_report())


@contextmanager
def measure_time(label: str, tracker: Optional[TimingTracker] = None):
    """Context manager to measure code execution time"""
    start = time.time()
    try:
        yield
    finally:
        elapsed_ms = (time.time() - start) * 1000
        print(f"[TIMING] ⏱️  {label}: {elapsed_ms:.0f}ms")
        if tracker:
            tracker.checkpoint(label)


def get_timing_tracker() -> TimingTracker:
    """Get a new timing tracker instance"""
    return TimingTracker()
