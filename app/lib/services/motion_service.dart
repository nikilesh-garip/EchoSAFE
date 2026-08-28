import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:sensors_plus/sensors_plus.dart';

/// Automatic "sudden motion" detector built on the device accelerometer.
///
/// This is additive evidence layered on top of the manual "Sudden motion
/// (panic)" toggle, following exactly the philosophy the backend already
/// uses for acoustic media-context detection on top of the manual
/// media-playback toggle (see model/audio_classes.py's
/// `MEDIA_CONTEXT_AUDIOSET_INDICES` comment and backend/main.py's
/// `_resolve_media_context`): the automatic signal only ever ADDS evidence,
/// it never overrides an explicit False from the user. [detected] is meant
/// to be OR'd with the manual toggle at the point the combined value is
/// actually sent to the backend -- this service never claims to replace it.
///
/// A "sudden motion" jolt is detected as a spike in the magnitude of the raw
/// accelerometer vector (x, y, z), which sits around 9.8 m/s^2 (gravity)
/// while the phone is at rest or carried normally. [_jerkThreshold] of
/// 20 m/s^2 total magnitude was picked as a sensible midpoint: ordinary
/// handling and walking rarely push the raw magnitude much past 12-15
/// m/s^2, while a fall, a hard drop, or someone breaking into a run
/// reliably spikes well past 20. Once a qualifying jolt is seen, [detected]
/// stays true for [_holdDuration] so a single spike reads as "motion
/// recently", then clears itself automatically -- it must never stay
/// pinned true from one old jolt.
class MotionService {
  MotionService({
    double jerkThreshold = 20.0,
    Duration holdDuration = const Duration(seconds: 5),
  })  : _jerkThreshold = jerkThreshold,
        _holdDuration = holdDuration;

  final double _jerkThreshold;
  final Duration _holdDuration;

  StreamSubscription<AccelerometerEvent>? _subscription;
  Timer? _decayTimer;

  /// True while a qualifying jolt was seen within the last [_holdDuration].
  /// Stays false permanently on any platform/permission failure -- see
  /// [start]. A [ValueNotifier] so callers can listen the same way the rest
  /// of the app listens to session/model-profile state.
  final ValueNotifier<bool> detected = ValueNotifier<bool>(false);

  /// Begins listening to the accelerometer. Safe to call even where no
  /// accelerometer exists (an emulator without sensor support, or a denied
  /// motion-sensor permission on some platforms): any failure -- thrown
  /// synchronously or delivered as a stream error -- is caught and logged,
  /// and [detected] simply stays false. A safety app must never fail to
  /// start, or block the rest of its context signals, because one optional
  /// sensor is unavailable.
  void start() {
    try {
      _subscription = accelerometerEventStream(
        samplingPeriod: SensorInterval.gameInterval,
      ).listen(
        _onEvent,
        onError: (Object error, StackTrace stackTrace) {
          debugPrint('MotionService: accelerometer stream error: $error');
        },
        cancelOnError: false,
      );
    } catch (error) {
      debugPrint('MotionService: could not start accelerometer stream: $error');
    }
  }

  void _onEvent(AccelerometerEvent event) {
    final magnitude = math.sqrt(
      event.x * event.x + event.y * event.y + event.z * event.z,
    );
    if (magnitude < _jerkThreshold) return;

    detected.value = true;
    _decayTimer?.cancel();
    _decayTimer = Timer(_holdDuration, () {
      detected.value = false;
    });
  }

  /// Stops the sensor subscription and any pending decay timer. Must be
  /// called from the owning State's dispose() to avoid leaking the stream
  /// subscription.
  void dispose() {
    _subscription?.cancel();
    _subscription = null;
    _decayTimer?.cancel();
    _decayTimer = null;
  }
}
