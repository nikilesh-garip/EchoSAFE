import os
import time
import numpy as np

def benchmark():
    print("================ OPENVINO BENCHMARK ================")
    xml_path = "checkpoints/openvino/echo_yamnet_model.xml"
    bin_path = "checkpoints/openvino/echo_yamnet_model.bin"
    
    if not os.path.exists(xml_path):
        raise FileNotFoundError(f"OpenVINO model files not found at: {xml_path}. Run export_openvino.py first.")
        
    import openvino as ov
    
    # 1. Model size
    xml_size = os.path.getsize(xml_path) / 1024
    bin_size = os.path.getsize(bin_path) / 1024
    print(f"Model Files Size:")
    print(f"  - XML (Structure): {xml_size:.2f} KB")
    print(f"  - BIN (Weights):   {bin_size:.2f} KB")
    print(f"  - Total IR Size:   {(xml_size + bin_size):.2f} KB")
    
    # 2. Core and compilation time
    print("\nInitializing OpenVINO Core...")
    core = ov.Core()
    
    devices = core.available_devices
    print(f"Available execution hardware targets: {devices}")
    
    # We benchmark CPU as baseline
    target_device = "CPU"
    print(f"\nCompiling model for target: {target_device}...")
    
    start_load = time.perf_counter()
    compiled_model = core.compile_model(xml_path, target_device)
    end_load = time.perf_counter()
    load_time_ms = (end_load - start_load) * 1000
    print(f"Model compilation / load time: {load_time_ms:.2f} ms")
    
    # Try GPU if available (Arc iGPU)
    gpu_available = "GPU" in devices
    if gpu_available:
        print("\nCompiling model for GPU (Intel Arc iGPU)...")
        try:
            start_load_gpu = time.perf_counter()
            compiled_model_gpu = core.compile_model(xml_path, "GPU")
            end_load_gpu = time.perf_counter()
            print(f"GPU model compilation time: {(end_load_gpu - start_load_gpu) * 1000:.2f} ms")
        except Exception as e:
            print(f"GPU compilation failed: {e}. iGPU might require driver configuration.")
            gpu_available = False
            
    # 3. Inference Latency Benchmark
    input_layer = compiled_model.input(0)
    output_layer = compiled_model.output(0)
    
    # Dummy input representing a 2-second raw waveform at 16kHz -- YAMNet
    # does its own internal framing/spectrogram extraction, so the exported
    # graph takes raw audio samples directly, not a precomputed spectrogram.
    dummy_input = np.random.randn(32000).astype(np.float32)
    
    # Warm-up runs
    print("\nPerforming warm-up runs...")
    for _ in range(50):
        _ = compiled_model([dummy_input])[0]
        
    # Timed runs
    iterations = 500
    print(f"Measuring average latency over {iterations} iterations on {target_device}...")
    
    latencies = []
    for _ in range(iterations):
        t_start = time.perf_counter()
        _ = compiled_model([dummy_input])[0]
        t_end = time.perf_counter()
        latencies.append((t_end - t_start) * 1000)
        
    avg_latency = np.mean(latencies)
    p50_latency = np.percentile(latencies, 50)
    p95_latency = np.percentile(latencies, 95)
    
    print("\n---------------- RESULTS ----------------")
    print(f"Average Inference Latency: {avg_latency:.3f} ms")
    print(f"50th Percentile Latency:   {p50_latency:.3f} ms")
    print(f"95th Percentile Latency:   {p95_latency:.3f} ms")
    print(f"Inferences Per Second:     {1000 / avg_latency:.1f} FPS")
    print("-----------------------------------------")
    
    # Repeat for GPU if available
    if gpu_available:
        print(f"\nMeasuring latency on Intel Arc GPU...")
        latencies_gpu = []
        for _ in range(iterations):
            t_start = time.perf_counter()
            _ = compiled_model_gpu([dummy_input])[0]
            t_end = time.perf_counter()
            latencies_gpu.append((t_end - t_start) * 1000)
        avg_latency_gpu = np.mean(latencies_gpu)
        print(f"GPU Average Latency: {avg_latency_gpu:.3f} ms")
        print(f"GPU Inferences/Sec:  {1000 / avg_latency_gpu:.1f} FPS")
        print("-----------------------------------------")
        
    print("\nOpenVINO Benchmark Completed Successfully!")

if __name__ == "__main__":
    benchmark()
