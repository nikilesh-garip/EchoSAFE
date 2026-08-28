Write-Host "Preparing dataset (real ESC-50/UrbanSound8K where available, labeled synthetic fallback otherwise)..."
python prepare_dataset.py

if ($LASTEXITCODE -ne 0) {
    Write-Error "Dataset preparation failed!"
    exit $LASTEXITCODE
}

Write-Host "Training YAMNet transfer-learning head..."
python train_yamnet.py

if ($LASTEXITCODE -ne 0) {
    Write-Error "Training failed!"
    exit $LASTEXITCODE
}

Write-Host "Evaluating on the held-out test split..."
python evaluate.py

if ($LASTEXITCODE -ne 0) {
    Write-Error "Evaluation failed!"
    exit $LASTEXITCODE
}

Write-Host "Pipeline completed successfully!"
