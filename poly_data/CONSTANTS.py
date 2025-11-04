# Configuration now centralized in config.py
# This file kept for backward compatibility

try:
    import config
    MIN_MERGE_SIZE = config.MIN_MERGE_SIZE
except ImportError:
    # Fallback if config not available
    MIN_MERGE_SIZE = 20
