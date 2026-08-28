import os
import datetime
import json

class StructuredLogger:
    def __init__(self, log_dir="../reports"):
        self.log_dir = os.path.abspath(log_dir)
        os.makedirs(self.log_dir, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file_path = os.path.join(self.log_dir, "training_run_trace.md")
        self.json_log_path = os.path.join(self.log_dir, f"training_run_trace_{timestamp}.json")

        self.entries = []
        self.start_time = datetime.datetime.now(datetime.timezone.utc)
        print(f"[Logger] Initialized. MD trace will be written to: {self.log_file_path}")

    def _flush(self):
        """Writes current log entries to disk in JSON and MD format."""
        try:
            # Write JSON log
            with open(self.json_log_path, "w", encoding="utf-8") as f:
                json.dump(self.entries, f, indent=2, ensure_ascii=False)

            # Write Markdown log
            self._write_markdown_file()
        except Exception as e:
            print(f"[Warning] Failed to flush logs to disk. Error: {e}")

    def _create_entry(self, entry_type, data):
        timestamp_str = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')
        return {
            "timestamp": timestamp_str,
            "type": entry_type,
            **data
        }

    def log_phase(self, phase_name):
        entry = self._create_entry("phase", {"name": phase_name})
        self.entries.append(entry)
        print(f"\n================ PHASE START: {phase_name.upper()} ================")
        self._flush()

    def log_task(self, task_name, message=""):
        entry = self._create_entry("task", {"name": task_name, "message": message})
        self.entries.append(entry)
        print(f"  [Task] {task_name}: {message}")
        self._flush()

    def log_event(self, event_type, details):
        entry = self._create_entry("event", {"event_type": event_type, "details": details})
        self.entries.append(entry)
        print(f"    [{event_type.upper()}] {details}")
        self._flush()

    def log_final_summary(self, summary_text):
        end_time = datetime.datetime.now(datetime.timezone.utc)
        duration = end_time - self.start_time
        entry = self._create_entry("final_summary", {
            "start_time": self.start_time.isoformat().replace('+00:00', 'Z'),
            "end_time": end_time.isoformat().replace('+00:00', 'Z'),
            "duration_seconds": duration.total_seconds(),
            "summary": summary_text
        })
        self.entries.append(entry)
        print(f"\n================ FINAL RUN SUMMARY ================\n{summary_text}\n")
        self._flush()

    def _write_markdown_file(self):
        with open(self.log_file_path, "w", encoding="utf-8") as f:
            f.write("# ECHO Model Training & Validation Run Trace\n\n")
            f.write(f"*Trace started at: {self.start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}*\n\n")
            
            for entry in self.entries:
                if entry["type"] == "phase":
                    f.write(f"\n## 🏁 PHASE: {entry['name'].upper()}\n")
                elif entry["type"] == "task":
                    f.write(f"\n### 📋 Task: {entry['name']}\n")
                    if entry['message']:
                        f.write(f"{entry['message']}\n")
                elif entry["type"] == "event":
                    f.write(f"* **[{entry['event_type'].upper()}]** {entry['details']}\n")
                elif entry["type"] == "final_summary":
                    f.write("\n---\n\n## 📈 Final Summary Report\n")
                    f.write(f"* **Duration**: {entry['duration_seconds']:.2f} seconds\n")
                    f.write(f"* **Start Time**: {entry['start_time']}\n")
                    f.write(f"* **End Time**: {entry['end_time']}\n\n")
                    f.write("### Metrics Details:\n")
                    f.write(f"```\n{entry['summary']}\n```\n")
