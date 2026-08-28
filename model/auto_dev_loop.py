import json
import os
import sys
import subprocess
import argparse
import time
from structured_logger import StructuredLogger
from metrics_tracker import MetricsTracker

def run_command(command_list):
    """Utility to run a CLI command safely."""
    try:
        result = subprocess.run(
            command_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        return True, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        return False, e.stdout, e.stderr

def parse_evaluation_metrics():
    """Reads evaluate.py's output report to extract test metrics."""
    report_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "reports", "evaluation_report.txt"))
    accuracy = 0.0
    f1_score = 0.0

    if os.path.exists(report_path):
        with open(report_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("Accuracy:"):
                    accuracy = float(line.split(":")[1].strip())
                elif line.startswith("F1 Score:"):
                    f1_score = float(line.split(":")[1].strip())

    return accuracy, f1_score

def read_training_history():
    """Reads train_yamnet.py's JSON results (final epoch's train/val loss+acc)."""
    results_path = os.path.join("checkpoints", "yamnet_training_results.json")
    if not os.path.exists(results_path):
        return -1, -1, -1
    with open(results_path, "r", encoding="utf-8") as f:
        results = json.load(f)
    history = results.get("history", {})
    train_loss = history.get("loss", [-1])[-1]
    val_loss = history.get("val_loss", [-1])[-1]
    val_acc = history.get("val_accuracy", [-1])[-1]
    return train_loss, val_loss, val_acc

def main():
    parser = argparse.ArgumentParser(description="Automated Dev Loop for ECHO model training and validation.")
    parser.add_argument("--target-f1", type=float, default=0.90, help="Target Test F1 score to pass the quality gate")
    parser.add_argument("--max-iterations", type=int, default=3, help="Maximum validation loop iterations")
    parser.add_argument("--epochs", type=int, default=80, help="Number of training epochs per iteration")
    args = parser.parse_args()

    logger = StructuredLogger(log_dir="../reports")
    tracker = MetricsTracker()

    logger.log_phase("Initial Setup")
    logger.log_task("Ingesting and Cleaning Dataset", "Executing prepare_dataset.py to map raw files to all 8 active classes...")

    # Step 1: Prep data
    success, stdout, stderr = run_command(["python", "prepare_dataset.py"])
    if not success:
        logger.log_event("failure", f"Dataset preparation failed: {stderr}")
        sys.exit(1)

    logger.log_event("success", "Successfully mapped and prepared datasets.")

    success_iteration = -1
    best_f1 = 0.0
    best_acc = 0.0

    # Only the classifier head is trained (YAMNet stays frozen), so these
    # iterations vary the head's own hyperparameters, not a backbone LR.
    learning_rates = [1e-3, 5e-4, 2e-4]

    for iteration in range(1, args.max_iterations + 1):
        lr = learning_rates[min(iteration - 1, len(learning_rates) - 1)]
        logger.log_phase(f"Validation Loop Iteration {iteration} (Learning Rate = {lr})")

        # 1. Train Model
        logger.log_task(f"Model Training (Iteration {iteration})", f"Training YAMNet classifier head for up to {args.epochs} epochs with LR={lr}...")
        t0 = time.time()
        success, stdout, stderr = run_command([
            "python", "train_yamnet.py",
            "--lr", str(lr),
            "--epochs", str(args.epochs),
        ])
        t_elapsed = time.time() - t0

        if not success:
            logger.log_event("failure", f"Training failed during iteration {iteration}: {stderr}")
            continue

        logger.log_event("success", f"Training completed in {t_elapsed:.1f}s.")

        train_loss, val_loss, val_acc = read_training_history()

        # 2. Evaluate Model
        logger.log_task(f"Model Evaluation (Iteration {iteration})", "Running evaluate.py on the test split...")
        success, stdout, stderr = run_command(["python", "evaluate.py"])
        if not success:
            logger.log_event("failure", f"Evaluation failed during iteration {iteration}: {stderr}")
            continue

        test_acc, test_f1 = parse_evaluation_metrics()
        logger.log_event("evaluation_metrics", f"Test Accuracy: {test_acc*100:.2f}%, Test F1 Score: {test_f1:.4f}")

        # Track metrics
        tracker.track_iteration(iteration, train_loss, val_loss, val_acc, test_f1, test_acc, lr)

        # 3. Check quality gate
        if test_f1 >= args.target_f1:
            logger.log_event("quality_gate_passed", f"Quality gate F1 score >= {args.target_f1} achieved!")
            success_iteration = iteration
            best_f1 = test_f1
            best_acc = test_acc
            break
        else:
            logger.log_event("quality_gate_failed", f"Iteration F1 score {test_f1:.4f} did not meet target {args.target_f1}.")
            if test_f1 > best_f1:
                best_f1 = test_f1
                best_acc = test_acc

    # Final summary report
    summary = tracker.get_summary()
    logger.log_final_summary(summary)

    logger.log_phase("Git Integration")
    if success_iteration != -1:
        logger.log_task("Committing Model", f"Staging checkpoints and reports, and creating git commit...")
        # Add files to git
        run_command(["git", "add", "checkpoints/yamnet_head.keras", "checkpoints/yamnet_training_results.json", "../reports/evaluation_report.txt", "../reports/training_run_trace.md"])

        # Create commit
        commit_msg = f"Automated Dev Loop Success: Test F1={best_f1:.4f}, Accuracy={best_acc*100:.2f}% (Iteration {success_iteration})"
        success, stdout, stderr = run_command(["git", "commit", "-m", commit_msg])
        if success:
            logger.log_event("git_commit_success", f"Successfully committed model checkpoint: {stdout.strip()}")
        else:
            logger.log_event("git_commit_failure", f"Failed to commit model files: {stderr}")
    else:
        logger.log_task("Dev Loop Finished with Failure", "The quality gate was not reached in any of the iterations. Not committing model checkpoints.")

if __name__ == "__main__":
    main()
