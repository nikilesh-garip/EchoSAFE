import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Staggered entrance: fade + short rise. Used to give each screen a sense of
/// order (header, then hero, then details) instead of everything snapping in
/// at once. Delay is capped so a long list never feels slow.
class FadeSlideIn extends StatefulWidget {
  final Widget child;
  final int index;
  final Duration stagger;
  final double offsetY;

  const FadeSlideIn({
    super.key,
    required this.child,
    this.index = 0,
    this.stagger = const Duration(milliseconds: 70),
    this.offsetY = 18,
  });

  @override
  State<FadeSlideIn> createState() => _FadeSlideInState();
}

class _FadeSlideInState extends State<FadeSlideIn> with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: AppDurations.slow,
  );

  @override
  void initState() {
    super.initState();
    final delayMs = (widget.stagger.inMilliseconds * widget.index).clamp(0, 600);
    Future.delayed(Duration(milliseconds: delayMs), () {
      if (mounted) _controller.forward();
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final curve = CurvedAnimation(parent: _controller, curve: Curves.easeOutCubic);
    return FadeTransition(
      opacity: curve,
      child: AnimatedBuilder(
        animation: curve,
        builder: (context, child) => Transform.translate(
          offset: Offset(0, widget.offsetY * (1 - curve.value)),
          child: child,
        ),
        child: widget.child,
      ),
    );
  }
}

/// Number that rolls to its new value instead of jumping.
class AnimatedCounter extends StatelessWidget {
  final num value;
  final TextStyle? style;
  final String suffix;
  final int decimals;

  const AnimatedCounter({
    super.key,
    required this.value,
    this.style,
    this.suffix = '',
    this.decimals = 0,
  });

  @override
  Widget build(BuildContext context) {
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: value.toDouble()),
      duration: AppDurations.slow,
      curve: Curves.easeOutCubic,
      builder: (context, animated, _) => Text(
        '${animated.toStringAsFixed(decimals)}$suffix',
        style: style,
      ),
    );
  }
}

/// Button that presses in slightly on tap. Small, but it makes the primary
/// actions on an emergency screen feel responsive under a shaking thumb.
class PressableScale extends StatefulWidget {
  final Widget child;
  final VoidCallback? onTap;

  const PressableScale({super.key, required this.child, this.onTap});

  @override
  State<PressableScale> createState() => _PressableScaleState();
}

class _PressableScaleState extends State<PressableScale> {
  double _scale = 1.0;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTapDown: (_) => setState(() => _scale = 0.97),
      onTapUp: (_) => setState(() => _scale = 1.0),
      onTapCancel: () => setState(() => _scale = 1.0),
      onTap: widget.onTap,
      child: AnimatedScale(
        scale: _scale,
        duration: AppDurations.fast,
        curve: Curves.easeOut,
        child: widget.child,
      ),
    );
  }
}

/// Slow horizontal gradient drift used behind hero panels and the login page.
class AnimatedGradientBackdrop extends StatefulWidget {
  final Widget child;
  final List<Color> colors;

  const AnimatedGradientBackdrop({super.key, required this.child, required this.colors});

  @override
  State<AnimatedGradientBackdrop> createState() => _AnimatedGradientBackdropState();
}

class _AnimatedGradientBackdropState extends State<AnimatedGradientBackdrop>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(seconds: 9),
  )..repeat(reverse: true);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        final t = Curves.easeInOut.transform(_controller.value);
        return Container(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment(-1 + 2 * t, -1),
              end: Alignment(1, 1 - 2 * t),
              colors: widget.colors,
            ),
          ),
          child: child,
        );
      },
      child: widget.child,
    );
  }
}
