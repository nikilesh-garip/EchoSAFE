import time

class MetricsTracker:
    def __init__(self):
        self.iterations = []
        self.start_time = time.time()

    def track_iteration(self, iteration, train_loss, val_loss, val_acc, test_f1, test_acc, lr):
        """Records metrics for a training iteration."""
        elapsed = time.time() - self.start_time
        data = {
            "iteration": iteration,
            "train_loss": train_loss,
            "val_loss": val_loss,
            "val_acc": val_acc,
            "test_f1": test_f1,
            "test_acc": test_acc,
            "learning_rate": lr,
            "elapsed_seconds": elapsed
        }
        self.iterations.append(data)

    def get_summary(self):
        """Returns a formatted summary of all tracked metrics across iterations."""
        if not self.iterations:
            return "No iterations were run."

        summary = "=" * 50 + "\n"
        summary += "AUTOMATED DEVELOPMENT LOOP METRICS REPORT\n"
        summary += "=" * 50 + "\n"
        
        for it in self.iterations:
            summary += (
                f"Iteration {it['iteration']}:\n"
                f"  - Learning Rate   : {it['learning_rate']:.5f}\n"
                f"  - Train Loss      : {it['train_loss']:.4f}\n"
                f"  - Val Loss        : {it['val_loss']:.4f}\n"
                f"  - Val Accuracy    : {it['val_acc'] * 100:.2f}%\n"
                f"  - Test F1 Score   : {it['test_f1']:.4f}\n"
                f"  - Test Accuracy   : {it['test_acc'] * 100:.2f}%\n"
                f"  - Elapsed Time    : {it['elapsed_seconds']:.1f}s\n"
                f"  " + "-" * 40 + "\n"
            )

        best_it = max(self.iterations, key=lambda x: x["test_f1"])
        summary += (
            f"*** BEST PERFORMANCE MODEL (Iteration {best_it['iteration']}) ***\n"
            f"  - Test F1 Score   : {best_it['test_f1']:.4f}\n"
            f"  - Test Accuracy   : {best_it['test_acc'] * 100:.2f}%\n"
            f"  - Final Val Acc   : {best_it['val_acc'] * 100:.2f}%\n"
            f"  - Final Val Loss  : {best_it['val_loss']:.4f}\n"
            f"Total duration: {time.time() - self.start_time:.2f} seconds\n"
        )
        summary += "=" * 50 + "\n"
        return summary
