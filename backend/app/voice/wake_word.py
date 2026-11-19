"""Optional wake-word integration placeholder.

Install and configure openWakeWord separately. Keep wake-word listening opt-in.
"""
class WakeWordListener:
    def start(self):
        raise NotImplementedError("Wake-word engine is optional and not configured.")

    def stop(self):
        return None
