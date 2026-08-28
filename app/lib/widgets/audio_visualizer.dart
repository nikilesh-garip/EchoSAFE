import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Live microphone visualiser.
///
/// Honesty note: this draws the **amplitude envelope** the recorder reports
/// (dBFS converted to 0..1), scrolled right-to-left, mirrored around the
/// centre line. It is not an FFT spectrum, and nothing here is labelled as
/// one -- a fake spectrogram on a safety product would be a lie told sixty
/// times a second. The per-bar shaping is interpolation between real samples,
/// not invented signal.
class LiveWaveform extends StatefulWidget {
  final double amplitude; // 0..1, latest microphone level
  final bool active;
  final Color color;
  final double height;
  final String? overlayLabel;

  const LiveWaveform({
    super.key,
    required this.amplitude,
    required this.active,
    this.color = AppColors.primary,
    this.height = 150,
    this.overlayLabel,
  });

  @override
  State<LiveWaveform> createState() => _LiveWaveformState();
}

class _LiveWaveformState extends State<LiveWaveform> with SingleTickerProviderStateMixin {
  static const _barCount = 56;

  late final AnimationController _controller;
  final List<double> _levels = List<double>.filled(_barCount, 0.0, growable: true);
  double _smoothed = 0.0;
  double _phase = 0.0;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1000),
    )..repeat();
    _controller.addListener(_onFrame);
  }

  void _onFrame() {
    // Exponential smoothing so a single loud frame does not make the whole
    // display jump, and the trace decays visibly instead of snapping to zero.
    final target = widget.active ? widget.amplitude.clamp(0.0, 1.0) : 0.0;
    _smoothed += (target - _smoothed) * (target > _smoothed ? 0.45 : 0.12);
    _phase += 0.06;

    _levels.removeAt(0);
    if (widget.active) {
      _levels.add(_smoothed);
    } else {
      // Idle breathing: a low, slow sine so the panel reads as "listening is
      // off" rather than "the app froze". Clearly below any real signal.
      _levels.add(0.045 + 0.03 * (0.5 + 0.5 * math.sin(_phase)));
    }
    setState(() {});
  }

  @override
  void dispose() {
    _controller.removeListener(_onFrame);
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: AppDurations.medium,
      height: widget.height,
      width: double.infinity,
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: widget.active
              ? [widget.color.withOpacity(0.10), AppColors.surface]
              : [AppColors.surfaceAlt, AppColors.surface],
        ),
        borderRadius: BorderRadius.circular(AppRadii.card),
        border: Border.all(
          color: widget.active ? widget.color.withOpacity(0.35) : AppColors.line,
        ),
      ),
      child: Stack(
        children: [
          Positioned.fill(
            child: RepaintBoundary(
              child: CustomPaint(
                painter: _WaveformPainter(
                  levels: List<double>.from(_levels),
                  color: widget.color,
                  active: widget.active,
                  phase: _phase,
                ),
              ),
            ),
          ),
          if (widget.overlayLabel != null)
            Positioned(
              left: 14,
              top: 12,
              child: Text(
                widget.overlayLabel!,
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.8,
                  color: widget.active ? widget.color : AppColors.inkFaint,
                ),
              ),
            ),
          Positioned(
            right: 14,
            top: 12,
            child: AnimatedOpacity(
              duration: AppDurations.medium,
              opacity: widget.active ? 1 : 0.35,
              child: Text(
                '${(widget.amplitude * 100).clamp(0, 100).toStringAsFixed(0)}%',
                style: const TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  color: AppColors.inkMuted,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _WaveformPainter extends CustomPainter {
  final List<double> levels;
  final Color color;
  final bool active;
  final double phase;

  _WaveformPainter({
    required this.levels,
    required this.color,
    required this.active,
    required this.phase,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final midY = size.height / 2;
    final barWidth = size.width / levels.length;
    final maxBar = size.height * 0.42;

    // Centre baseline
    final baseline = Paint()
      ..color = AppColors.line
      ..strokeWidth = 1;
    canvas.drawLine(Offset(0, midY), Offset(size.width, midY), baseline);

    for (var i = 0; i < levels.length; i++) {
      final level = levels[i].clamp(0.0, 1.0);
      // Newer samples (right side) are drawn at full opacity; older ones fade,
      // which gives the trace direction without any extra chrome.
      final age = i / levels.length;
      final height = math.max(2.0, level * maxBar);
      final x = i * barWidth + barWidth / 2;

      final paint = Paint()
        ..strokeCap = StrokeCap.round
        ..strokeWidth = math.max(2.0, barWidth * 0.55)
        ..shader = LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            Color.lerp(color, AppColors.accent, level.clamp(0.0, 1.0) * 0.8)!
                .withOpacity(active ? (0.25 + 0.75 * age) : 0.35),
            color.withOpacity(active ? (0.18 + 0.5 * age) : 0.2),
          ],
        ).createShader(Rect.fromLTWH(x - 2, midY - height, 4, height * 2));

      canvas.drawLine(Offset(x, midY - height), Offset(x, midY + height), paint);
    }

    if (!active) return;

    // Leading-edge marker at the newest sample.
    final headLevel = levels.last.clamp(0.0, 1.0);
    final headX = size.width - barWidth / 2;
    final glow = Paint()
      ..color = AppColors.accent.withOpacity(0.18 + 0.12 * math.sin(phase * 2))
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 8);
    canvas.drawCircle(Offset(headX, midY), 10 + 14 * headLevel, glow);
  }

  @override
  bool shouldRepaint(covariant _WaveformPainter oldDelegate) => true;
}

/// Radial "listening" pulse used on the dashboard hero.
class PulseRing extends StatefulWidget {
  final bool active;
  final Color color;
  final double size;
  final Widget child;

  const PulseRing({
    super.key,
    required this.active,
    required this.child,
    this.color = AppColors.primary,
    this.size = 168,
  });

  @override
  State<PulseRing> createState() => _PulseRingState();
}

class _PulseRingState extends State<PulseRing> with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: AppDurations.pulse,
  )..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: widget.size,
      height: widget.size,
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, child) {
          return CustomPaint(
            painter: _PulsePainter(
              progress: _controller.value,
              color: widget.color,
              active: widget.active,
            ),
            child: Center(child: child),
          );
        },
        child: widget.child,
      ),
    );
  }
}

class _PulsePainter extends CustomPainter {
  final double progress;
  final Color color;
  final bool active;

  _PulsePainter({required this.progress, required this.color, required this.active});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final baseRadius = size.width * 0.28;

    final ring = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4
      ..color = color.withOpacity(active ? 0.25 : 0.12);
    canvas.drawCircle(center, baseRadius, ring);

    if (!active) return;

    // Three expanding rings, evenly offset in phase.
    for (var i = 0; i < 3; i++) {
      final t = (progress + i / 3) % 1.0;
      final radius = baseRadius + t * (size.width / 2 - baseRadius);
      final paint = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.0 * (1 - t) + 0.5
        ..color = color.withOpacity((1 - t) * 0.45);
      canvas.drawCircle(center, radius, paint);
    }
  }

  @override
  bool shouldRepaint(covariant _PulsePainter oldDelegate) =>
      oldDelegate.progress != progress || oldDelegate.active != active;
}

/// Animated 0-100 risk arc.
class RiskGauge extends StatelessWidget {
  final int score;
  final String level;
  final double size;

  const RiskGauge({super.key, required this.score, required this.level, this.size = 132});

  @override
  Widget build(BuildContext context) {
    final color = AppColors.forRiskLevel(level);
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: score.clamp(0, 100) / 100),
      duration: AppDurations.slow,
      curve: Curves.easeOutCubic,
      builder: (context, value, _) {
        return SizedBox(
          width: size,
          height: size,
          child: CustomPaint(
            painter: _GaugePainter(value: value, color: color),
            child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    '${(value * 100).round()}',
                    style: TextStyle(
                      fontSize: size * 0.26,
                      fontWeight: FontWeight.w800,
                      color: color,
                      height: 1,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    'RISK',
                    style: TextStyle(
                      fontSize: 10,
                      letterSpacing: 1.4,
                      fontWeight: FontWeight.w700,
                      color: AppColors.inkMuted,
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class _GaugePainter extends CustomPainter {
  final double value;
  final Color color;

  _GaugePainter({required this.value, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    final center = rect.center;
    final radius = size.width / 2 - 10;
    const startAngle = math.pi * 0.75;
    const sweep = math.pi * 1.5;

    final track = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 11
      ..strokeCap = StrokeCap.round
      ..color = AppColors.line;
    canvas.drawArc(Rect.fromCircle(center: center, radius: radius), startAngle, sweep, false, track);

    final progress = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 11
      ..strokeCap = StrokeCap.round
      ..shader = SweepGradient(
        startAngle: startAngle,
        endAngle: startAngle + sweep,
        colors: [color.withOpacity(0.45), color],
      ).createShader(Rect.fromCircle(center: center, radius: radius));
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      startAngle,
      sweep * value,
      false,
      progress,
    );
  }

  @override
  bool shouldRepaint(covariant _GaugePainter oldDelegate) =>
      oldDelegate.value != value || oldDelegate.color != color;
}

/// Countdown ring for the escalation cancel window.
class CountdownRing extends StatelessWidget {
  final double remainingSeconds;
  final double totalSeconds;
  final double size;

  const CountdownRing({
    super.key,
    required this.remainingSeconds,
    required this.totalSeconds,
    this.size = 108,
  });

  @override
  Widget build(BuildContext context) {
    final fraction = totalSeconds <= 0 ? 0.0 : (remainingSeconds / totalSeconds).clamp(0.0, 1.0);
    return SizedBox(
      width: size,
      height: size,
      child: TweenAnimationBuilder<double>(
        tween: Tween(begin: fraction, end: fraction),
        duration: AppDurations.fast,
        builder: (context, value, _) => CustomPaint(
          painter: _CountdownPainter(value: value),
          child: Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  remainingSeconds.ceil().toString(),
                  style: const TextStyle(
                    fontSize: 32,
                    fontWeight: FontWeight.w800,
                    color: AppColors.danger,
                    height: 1,
                  ),
                ),
                const Text(
                  'sec',
                  style: TextStyle(fontSize: 11, color: AppColors.inkMuted),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _CountdownPainter extends CustomPainter {
  final double value;
  _CountdownPainter({required this.value});

  @override
  void paint(Canvas canvas, Size size) {
    final center = size.center(Offset.zero);
    final radius = size.width / 2 - 8;

    canvas.drawCircle(
      center,
      radius,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 9
        ..color = AppColors.dangerSoft,
    );
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      -math.pi / 2,
      2 * math.pi * value,
      false,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 9
        ..strokeCap = StrokeCap.round
        ..color = AppColors.danger,
    );
  }

  @override
  bool shouldRepaint(covariant _CountdownPainter oldDelegate) => oldDelegate.value != value;
}
