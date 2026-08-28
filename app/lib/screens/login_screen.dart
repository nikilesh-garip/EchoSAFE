import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../services/session_service.dart';
import '../theme/app_theme.dart';
import '../widgets/animations.dart';

/// Sign-in shell.
///
/// This does not authenticate anything: whatever is entered is accepted, and
/// the credentials never leave the device. It exists so the app has a real
/// account identity -- a stable user id that scopes contacts, history, and
/// incidents, and a display name that goes into the message an emergency
/// contact actually receives ("Mahendhar may be in danger"). The card at the
/// bottom of the form says exactly that, because a login screen that looks
/// like security but is not would be worse than no login screen at all.
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> with SingleTickerProviderStateMixin {
  final _formKey = GlobalKey<FormState>();
  final _identifierController = TextEditingController();
  final _nameController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _obscure = true;
  bool _busy = false;

  late final AnimationController _logoController = AnimationController(
    vsync: this,
    duration: const Duration(seconds: 4),
  )..repeat();

  @override
  void dispose() {
    _identifierController.dispose();
    _nameController.dispose();
    _passwordController.dispose();
    _logoController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() => _busy = true);
    await AppSession.instance.signIn(
      identifier: _identifierController.text,
      displayName: _nameController.text,
    );
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: AnimatedGradientBackdrop(
        colors: const [Color(0xFFE6FFFB), AppColors.canvas, Color(0xFFEFF6FF)],
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 460),
                child: Form(
                  key: _formKey,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      FadeSlideIn(index: 0, child: _buildLogo()),
                      const SizedBox(height: 26),
                      const FadeSlideIn(
                        index: 1,
                        child: Text(
                          'ECHO',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontSize: 40,
                            fontWeight: FontWeight.w900,
                            letterSpacing: 8,
                            color: AppColors.ink,
                          ),
                        ),
                      ),
                      const SizedBox(height: 8),
                      const FadeSlideIn(
                        index: 2,
                        child: Text(
                          'Acoustic hazard detection that calls the people who can help.',
                          textAlign: TextAlign.center,
                          style: TextStyle(fontSize: 14, color: AppColors.inkMuted, height: 1.5),
                        ),
                      ),
                      const SizedBox(height: 34),
                      FadeSlideIn(
                        index: 3,
                        child: AppCard(
                          padding: const EdgeInsets.fromLTRB(20, 24, 20, 24),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              const Text(
                                'Sign in',
                                style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
                              ),
                              const SizedBox(height: 4),
                              const Text(
                                'Your identity is stored on this device only.',
                                style: TextStyle(fontSize: 13, color: AppColors.inkMuted),
                              ),
                              const SizedBox(height: 22),
                              TextFormField(
                                controller: _identifierController,
                                keyboardType: TextInputType.emailAddress,
                                textInputAction: TextInputAction.next,
                                decoration: const InputDecoration(
                                  labelText: 'Email or phone',
                                  prefixIcon: Icon(Icons.alternate_email, size: 20),
                                ),
                                validator: (value) => (value == null || value.trim().isEmpty)
                                    ? 'Enter an email or phone number'
                                    : null,
                              ),
                              const SizedBox(height: 14),
                              TextFormField(
                                controller: _nameController,
                                textInputAction: TextInputAction.next,
                                decoration: const InputDecoration(
                                  labelText: 'Display name (optional)',
                                  helperText: 'Used in the alert your contacts receive',
                                  prefixIcon: Icon(Icons.badge_outlined, size: 20),
                                ),
                              ),
                              const SizedBox(height: 14),
                              TextFormField(
                                controller: _passwordController,
                                obscureText: _obscure,
                                onFieldSubmitted: (_) => _submit(),
                                decoration: InputDecoration(
                                  labelText: 'Password',
                                  prefixIcon: const Icon(Icons.lock_outline, size: 20),
                                  suffixIcon: IconButton(
                                    icon: Icon(
                                      _obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined,
                                      size: 20,
                                    ),
                                    onPressed: () => setState(() => _obscure = !_obscure),
                                  ),
                                ),
                                validator: (value) => (value == null || value.isEmpty)
                                    ? 'Enter any password'
                                    : null,
                              ),
                              const SizedBox(height: 22),
                              PressableScale(
                                child: ElevatedButton(
                                  onPressed: _busy ? null : _submit,
                                  child: _busy
                                      ? const SizedBox(
                                          height: 20,
                                          width: 20,
                                          child: CircularProgressIndicator(
                                            strokeWidth: 2,
                                            color: Colors.white,
                                          ),
                                        )
                                      : const Text('ENTER ECHO'),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                      const SizedBox(height: 18),
                      FadeSlideIn(
                        index: 4,
                        child: AppCard(
                          background: AppColors.infoSoft,
                          borderColor: const Color(0xFFBFDBFE),
                          padding: const EdgeInsets.all(16),
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: const [
                              Icon(Icons.info_outline, size: 18, color: AppColors.info),
                              SizedBox(width: 10),
                              Expanded(
                                child: Text(
                                  'Demo sign-in: any credentials are accepted and nothing is sent '
                                  'anywhere. This creates a local profile so your contacts, history, '
                                  'and alerts stay together.',
                                  style: TextStyle(
                                    fontSize: 12,
                                    height: 1.5,
                                    color: Color(0xFF1E3A8A),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildLogo() {
    return SizedBox(
      height: 132,
      child: AnimatedBuilder(
        animation: _logoController,
        builder: (context, _) => CustomPaint(
          painter: _LogoPainter(_logoController.value),
          child: const Center(
            child: Icon(Icons.graphic_eq_rounded, size: 46, color: AppColors.primary),
          ),
        ),
      ),
    );
  }
}

class _LogoPainter extends CustomPainter {
  final double t;
  _LogoPainter(this.t);

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    for (var i = 0; i < 4; i++) {
      final phase = (t + i / 4) % 1.0;
      final radius = 34 + phase * 44;
      canvas.drawCircle(
        center,
        radius,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.8 * (1 - phase) + 0.3
          ..color = AppColors.primary.withOpacity((1 - phase) * 0.5),
      );
    }
    canvas.drawCircle(
      center,
      30 + 1.5 * math.sin(t * 2 * math.pi),
      Paint()..color = AppColors.primarySoft,
    );
  }

  @override
  bool shouldRepaint(covariant _LogoPainter oldDelegate) => oldDelegate.t != t;
}
