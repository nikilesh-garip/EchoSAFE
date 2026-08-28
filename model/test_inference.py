import os
import requests

def test_api():
    # Override with ECHO_API_URL when the backend is not on the default port
    base_url = os.environ.get("ECHO_API_URL", "http://127.0.0.1:8010")
    url = f"{base_url}/detect"

    # Find first siren or glass breaking file dynamically
    import glob
    data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "data"))

    test_files = []
    # Prefer real ingested audio, fall back to the synthetic generator output
    for source in ("processed", "synthetic"):
        for class_name in ("siren", "glass_breaking"):
            test_files = glob.glob(os.path.join(data_dir, source, class_name, "*.wav"))
            if test_files:
                break
        if test_files:
            break

    if not test_files:
        print("No test files available yet. Run generate_synthetic_data.py or prepare_dataset.py first.")
        return
        
    test_file = test_files[0]
            
    print(f"Testing API with real audio file: {test_file}")
    
    with open(test_file, "rb") as f:
        files = {"file": ("test.wav", f, "audio/wav")}
        data = {
            "duration": 5.0, # Send 5s to trigger both Pass 1 and Pass 2
            "media_playback": False,
            "sudden_motion": False
        }
        
        try:
            response = requests.post(url, files=files, data=data)
            print(f"Status Code: {response.status_code}")
            import json
            print(f"Response: {json.dumps(response.json(), indent=2)}")
        except Exception as e:
            print(f"Failed to connect to API: {e}")

if __name__ == "__main__":
    test_api()
