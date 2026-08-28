import os
import numpy as np
import soundfile as sf

def generate_gunshot(duration=2.0, sr=16000):
    """No real gunshot audio is available to this pipeline (see
    docs/SAFETY_IMPLEMENTATION_PLAN.md); this stays a synthetic fallback,
    never a substitute for real evidence (model_readiness.py enforces that).
    Randomized per-call so 150 calls do not collapse into 150 near-identical
    spectral templates: a real gunshot is a very fast-attack broadband
    impulse (the muzzle blast) plus a slower environmental tail
    (echo/reverberation), sometimes with a second, fainter report."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    attack_decay = np.random.uniform(35, 60)
    tail_decay = np.random.uniform(4, 9)
    tail_mix = np.random.uniform(0.15, 0.35)
    crack = np.random.normal(0, 0.6, len(t)) * np.exp(-attack_decay * t)
    tail = np.random.normal(0, 0.4, len(t)) * np.exp(-tail_decay * t)
    signal = crack + tail_mix * tail
    if np.random.random() < 0.35 and duration > 0.3:
        delay = np.random.uniform(0.08, min(0.25, duration - 0.1))
        idx = int(delay * sr)
        echo_decay = np.random.uniform(20, 40)
        tail_t = t[idx:] - delay
        signal[idx:] += 0.4 * np.random.normal(0, 0.5, len(tail_t)) * np.exp(-echo_decay * tail_t)
    return signal

def generate_explosion(duration=3.0, sr=16000):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # Low frequency rumble + exponential decay noise, randomized per call.
    decay = np.exp(-np.random.uniform(2.0, 4.5) * t)
    noise = np.random.normal(0, np.random.uniform(0.3, 0.5), len(t))
    rumble_freq = np.random.uniform(35, 70)
    rumble = np.sin(2 * np.pi * rumble_freq * t) * np.exp(-np.random.uniform(0.7, 1.5) * t)
    signal = (noise * decay) + np.random.uniform(0.4, 0.7) * rumble
    return signal

def generate_scream(duration=2.0, sr=16000):
    """No real scream audio is available to this pipeline. A real scream's
    pitch contour and vibrato rate vary a lot between people and takes;
    randomizing the fundamental, vibrato depth/rate, and harmonic mix per
    call gives the fallback more spread instead of one fixed "siren voice"."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    base_freq = np.random.uniform(900, 1600)
    vibrato_depth = np.random.uniform(200, 400)
    vibrato_rate = np.random.uniform(5, 11)
    f_mod = base_freq + vibrato_depth * np.sin(2 * np.pi * vibrato_rate * t)
    phase = 2 * np.pi * np.cumsum(f_mod) / sr
    h2 = np.random.uniform(0.35, 0.65)
    h3 = np.random.uniform(0.15, 0.35)
    signal = np.sin(phase) + h2 * np.sin(2 * phase) + h3 * np.sin(3 * phase)
    signal += np.random.normal(0, np.random.uniform(0.12, 0.25), len(t))
    # Fade in/out shape varies too -- not every scream is a symmetric arc.
    fade_power = np.random.uniform(0.7, 1.4)
    signal = signal * np.sin(np.pi * t / duration) ** fade_power
    return signal

def generate_glass_breaking(duration=2.0, sr=16000):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # Multiple sharp impulses at high frequency
    signal = np.zeros_like(t)
    for _ in range(10):
        start_time = np.random.uniform(0.1, 1.2)
        idx = int(start_time * sr)
        # decaying high frequency tone
        t_decay = t[idx:] - start_time
        decay = np.exp(-25 * t_decay)
        freq = np.random.uniform(3000, 6000)
        signal[idx:] += np.sin(2 * np.pi * freq * t_decay) * decay * np.random.uniform(0.3, 0.8)
    # Add minor noise
    signal += np.random.normal(0, 0.05, len(t))
    return signal

def generate_fire_alarm(duration=3.0, sr=16000):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # Beeping pure tone (e.g. 3000 Hz)
    beep_freq = 3000
    beep_signal = np.sin(2 * np.pi * beep_freq * t)
    # Square wave envelope (0.3s on, 0.3s off)
    envelope = (np.sin(2 * np.pi * (1 / 0.6) * t) > 0).astype(float)
    signal = beep_signal * envelope
    return signal

def generate_siren(duration=3.0, sr=16000):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # Wailing siren: FM sweep between 600 and 1200 Hz
    f_mod = 900 + 300 * np.sin(2 * np.pi * 0.5 * t) # 2 sec cycle
    phase = 2 * np.pi * np.cumsum(f_mod) / sr
    signal = np.sin(phase)
    return signal

def generate_shouting(duration=2.5, sr=16000):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # Modulated low frequency vocal simulation
    f_mod = 250 + 50 * np.sin(2 * np.pi * 10 * t)
    phase = 2 * np.pi * np.cumsum(f_mod) / sr
    signal = np.sin(phase) + 0.3 * np.sin(3 * phase)
    # Turn it into intermittent bursts of shout
    envelope = (np.sin(2 * np.pi * 1.5 * t) > 0.1).astype(float)
    signal = signal * envelope + np.random.normal(0, 0.15, len(t))
    return signal


def generate_firecracker(duration=5.0, sr=16000):
    """Synthetic Diwali-style cracker audio for the demo profile.

    Deliberately shaped to be acoustically *distinct* from generate_gunshot:
    a gunshot is one impulse with a longer tail, while a cracker chain
    ("ladi") is a rapid train of very short, bright pops with occasional
    louder aerial bursts. Keeping the two synthetic signatures separable is
    the whole point -- if the fallback data made them look alike, the demo
    head would learn nothing useful and the production head's firecracker
    rejection could not be measured at all.

    This is fallback data only. Real recordings dropped into
    model/data/raw/firecrackers/ always take priority (see
    prepare_demo_dataset.py).
    """
    n = int(sr * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    signal = np.zeros(n)

    # Chain of rapid pops
    position = np.random.uniform(0.05, 0.4)
    while position < duration - 0.15:
        idx = int(position * sr)
        tail = t[idx:] - position
        # Very fast decay (~25 ms) and a bright, noisy body: a cracker pop is
        # shorter and higher-centred than a gunshot's muzzle blast.
        decay = np.exp(-120 * tail)
        pop = np.random.normal(0, 1.0, len(tail)) * decay
        crack = np.sin(2 * np.pi * np.random.uniform(1800, 4500) * tail) * np.exp(-160 * tail)
        signal[idx:] += (pop + 0.6 * crack) * np.random.uniform(0.5, 1.0)
        position += np.random.uniform(0.04, 0.22)

    # Occasional aerial shell: louder, with a low thump under it
    for _ in range(np.random.randint(1, 3)):
        position = np.random.uniform(0.2, max(0.3, duration - 1.0))
        idx = int(position * sr)
        tail = t[idx:] - position
        thump = np.sin(2 * np.pi * 70 * tail) * np.exp(-9 * tail)
        burst = np.random.normal(0, 1.0, len(tail)) * np.exp(-35 * tail)
        signal[idx:] += 1.3 * burst + 0.8 * thump

    # Distant crowd/ambience floor, which real Diwali audio always has
    signal += np.random.normal(0, 0.02, n)
    return signal

def generate_normal(duration=3.0, sr=16000):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # Low level white noise (or clean background)
    signal = np.random.normal(0, 0.02, len(t))
    return signal

def build_firecracker_set(base_dir="data/synthetic", samples=80):
    """Writes only the demo-profile firecracker class.

    Kept out of build_dataset's generator map on purpose: the production
    manifest walks the eight production classes, so this folder can never
    leak into the production training set.
    """
    class_dir = os.path.join(base_dir, "firecracker")
    os.makedirs(class_dir, exist_ok=True)
    print("Generating synthetic firecracker fallback clips (demo profile)...")
    for i in range(samples):
        duration = np.random.uniform(4.5, 5.0)
        audio = generate_firecracker(duration=duration)
        peak = np.max(np.abs(audio))
        if peak > 0:
            audio = audio / peak * 0.9
        sf.write(os.path.join(class_dir, "firecracker_{:03d}.wav".format(i)), audio, 16000)
    print("Wrote {} synthetic firecracker clips to {}".format(samples, class_dir))


def build_dataset(base_dir="data/synthetic", samples_per_class=150):
    os.makedirs(base_dir, exist_ok=True)
    
    generators = {
        "gunshot": generate_gunshot,
        "explosion": generate_explosion,
        "scream": generate_scream,
        "glass_breaking": generate_glass_breaking,
        "fire_alarm": generate_fire_alarm,
        "siren": generate_siren,
        "shouting": generate_shouting,
        "normal": generate_normal
    }
    
    metadata = []
    
    for class_name, gen_func in generators.items():
        class_dir = os.path.join(base_dir, class_name)
        os.makedirs(class_dir, exist_ok=True)
        print(f"Generating synthetic sounds for class: {class_name}...")
        
        for i in range(samples_per_class):
            filename = f"{class_name}_{i:03d}.wav"
            filepath = os.path.join(class_dir, filename)
            # Clips must cover the full 5s Pass 2 verification window. Training only ever
            # reads the first 2s (dataset.py truncates), so longer clips cost nothing there,
            # but a shorter clip gets zero-padded at verification time and fails the 0.70 check.
            duration = np.random.uniform(4.5, 5.0)
            audio = gen_func(duration=duration)
            # Normalize
            if np.max(np.abs(audio)) > 0:
                audio = audio / np.max(np.abs(audio)) * 0.9
            sf.write(filepath, audio, 16000)
            
            # Save relative or full path + label
            metadata.append((filepath, class_name))
            
    # Save a metadata txt/csv for dataset loader
    metadata_path = os.path.join(base_dir, "metadata.csv")
    with open(metadata_path, "w") as f:
        for path, label in metadata:
            # write absolute/relative path
            f.write(f"{path},{label}\n")
            
    print(f"Dataset generation complete! Created {len(metadata)} samples in {base_dir}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--firecracker-only", action="store_true",
                        help="Generate only the demo-profile firecracker fallback class.")
    parser.add_argument("--samples-per-class", type=int, default=150)
    args = parser.parse_args()
    if args.firecracker_only:
        build_firecracker_set()
    else:
        build_dataset(samples_per_class=args.samples_per_class)
        build_firecracker_set()
