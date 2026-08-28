import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Echo's design tokens and light theme.
///
/// The app used to be dark slate. A safety product is read in a hurry, often
/// outdoors in daylight, and often by a panel of people looking at a phone
/// held by someone else -- a light, high-contrast surface with one saturated
/// alarm colour reads faster in all three situations. Colour is used
/// sparingly on purpose: if teal, orange, amber and red all appear on a calm
/// screen, none of them mean anything when a real alert arrives.
class AppColors {
  static const canvas = Color(0xFFF4F6FA);
  static const surface = Color(0xFFFFFFFF);
  static const surfaceAlt = Color(0xFFEEF2F7);

  static const primary = Color(0xFF0F766E); // teal 700
  static const primarySoft = Color(0xFFCCFBF1);
  static const accent = Color(0xFFF97316); // orange 500

  static const danger = Color(0xFFDC2626);
  static const dangerSoft = Color(0xFFFEE2E2);
  static const warning = Color(0xFFD97706);
  static const warningSoft = Color(0xFFFEF3C7);
  static const success = Color(0xFF15803D);
  static const successSoft = Color(0xFFDCFCE7);
  static const info = Color(0xFF2563EB);
  static const infoSoft = Color(0xFFDBEAFE);

  static const ink = Color(0xFF0F172A);
  static const inkMuted = Color(0xFF64748B);
  static const inkFaint = Color(0xFF94A3B8);
  static const line = Color(0xFFE2E8F0);

  /// Risk levels get one consistent colour across every screen, so a user
  /// learns the scale once rather than per-screen.
  static Color forRiskLevel(String level) {
    switch (level.toUpperCase()) {
      case 'HIGH_RISK':
        return danger;
      case 'POSSIBLE_DANGER':
        return accent;
      case 'SUSPICIOUS':
        return warning;
      default:
        return success;
    }
  }

  static Color softForRiskLevel(String level) {
    switch (level.toUpperCase()) {
      case 'HIGH_RISK':
        return dangerSoft;
      case 'POSSIBLE_DANGER':
        return const Color(0xFFFFEDD5);
      case 'SUSPICIOUS':
        return warningSoft;
      default:
        return successSoft;
    }
  }
}

class AppDurations {
  static const fast = Duration(milliseconds: 180);
  static const medium = Duration(milliseconds: 320);
  static const slow = Duration(milliseconds: 620);
  static const pulse = Duration(milliseconds: 2200);
}

class AppRadii {
  static const card = 20.0;
  static const control = 14.0;
  static const pill = 999.0;
}

/// Soft, low-contrast elevation. Heavy Material shadows look dated and, on a
/// light canvas, muddy the colour that actually matters.
List<BoxShadow> softShadow({double opacity = 0.06, double blur = 24, double y = 8}) => [
      BoxShadow(
        color: AppColors.ink.withOpacity(opacity),
        blurRadius: blur,
        offset: Offset(0, y),
      ),
    ];

class AppTheme {
  static ThemeData light() {
    final base = ThemeData.light(useMaterial3: true);
    final scheme = ColorScheme.fromSeed(
      seedColor: AppColors.primary,
      brightness: Brightness.light,
    ).copyWith(
      primary: AppColors.primary,
      secondary: AppColors.accent,
      error: AppColors.danger,
      surface: AppColors.surface,
    );

    return base.copyWith(
      colorScheme: scheme,
      scaffoldBackgroundColor: AppColors.canvas,
      splashFactory: InkSparkle.splashFactory,
      textTheme: base.textTheme.apply(
        bodyColor: AppColors.ink,
        displayColor: AppColors.ink,
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: AppColors.canvas,
        foregroundColor: AppColors.ink,
        elevation: 0,
        centerTitle: false,
        systemOverlayStyle: SystemUiOverlayStyle.dark,
        titleTextStyle: TextStyle(
          color: AppColors.ink,
          fontSize: 20,
          fontWeight: FontWeight.w700,
        ),
      ),
      // Card styling lives in AppCard rather than ThemeData.cardTheme: the
      // type of that field changed between Flutter versions (CardTheme ->
      // CardThemeData), and this app should not fail to compile over a
      // theme entry nothing uses.
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: AppColors.primary,
          foregroundColor: Colors.white,
          elevation: 0,
          minimumSize: const Size.fromHeight(52),
          textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700, letterSpacing: 0.2),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppRadii.control)),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: AppColors.primary,
          minimumSize: const Size.fromHeight(52),
          side: const BorderSide(color: AppColors.line),
          textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppRadii.control)),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(foregroundColor: AppColors.primary),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: AppColors.surfaceAlt,
        hintStyle: const TextStyle(color: AppColors.inkFaint, fontSize: 14),
        labelStyle: const TextStyle(color: AppColors.inkMuted, fontSize: 14),
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadii.control),
          borderSide: BorderSide.none,
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadii.control),
          borderSide: const BorderSide(color: AppColors.line),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadii.control),
          borderSide: const BorderSide(color: AppColors.primary, width: 1.6),
        ),
      ),
      switchTheme: SwitchThemeData(
        thumbColor: WidgetStateProperty.resolveWith(
          (states) => states.contains(WidgetState.selected) ? Colors.white : AppColors.inkFaint,
        ),
        trackColor: WidgetStateProperty.resolveWith(
          (states) => states.contains(WidgetState.selected) ? AppColors.primary : AppColors.line,
        ),
      ),
      sliderTheme: const SliderThemeData(
        activeTrackColor: AppColors.primary,
        inactiveTrackColor: AppColors.line,
        thumbColor: AppColors.primary,
      ),
      dividerTheme: const DividerThemeData(color: AppColors.line, thickness: 1, space: 1),
      chipTheme: base.chipTheme.copyWith(
        backgroundColor: AppColors.surfaceAlt,
        side: const BorderSide(color: AppColors.line),
        labelStyle: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: AppColors.ink,
        contentTextStyle: const TextStyle(color: Colors.white),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppRadii.control)),
      ),
      pageTransitionsTheme: const PageTransitionsTheme(builders: {
        TargetPlatform.android: _FadeThroughTransitionBuilder(),
        TargetPlatform.iOS: _FadeThroughTransitionBuilder(),
      }),
    );
  }
}

/// Shared push transition: a short fade with a small upward slide. Material's
/// default Android transition is heavier than this app's motion language.
class _FadeThroughTransitionBuilder extends PageTransitionsBuilder {
  const _FadeThroughTransitionBuilder();

  @override
  Widget buildTransitions<T>(
    PageRoute<T> route,
    BuildContext context,
    Animation<double> animation,
    Animation<double> secondaryAnimation,
    Widget child,
  ) {
    final curved = CurvedAnimation(parent: animation, curve: Curves.easeOutCubic);
    return FadeTransition(
      opacity: curved,
      child: SlideTransition(
        position: Tween<Offset>(begin: const Offset(0, 0.035), end: Offset.zero).animate(curved),
        child: child,
      ),
    );
  }
}

/// Section label used across screens.
class SectionLabel extends StatelessWidget {
  final String text;
  final Widget? trailing;
  const SectionLabel(this.text, {super.key, this.trailing});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            text.toUpperCase(),
            style: const TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w800,
              letterSpacing: 1.1,
              color: AppColors.inkMuted,
            ),
          ),
          if (trailing != null) trailing!,
        ],
      ),
    );
  }
}

/// White card with a hairline border and soft shadow.
class AppCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;
  final Color? background;
  final Color? borderColor;
  final VoidCallback? onTap;

  const AppCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(18),
    this.background,
    this.borderColor,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final content = AnimatedContainer(
      duration: AppDurations.medium,
      curve: Curves.easeOut,
      padding: padding,
      decoration: BoxDecoration(
        color: background ?? AppColors.surface,
        borderRadius: BorderRadius.circular(AppRadii.card),
        border: Border.all(color: borderColor ?? AppColors.line),
        boxShadow: softShadow(),
      ),
      child: child,
    );
    if (onTap == null) return content;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(AppRadii.card),
      child: content,
    );
  }
}

/// Small status pill (ACTIVE / DEMO / HIGH RISK ...).
class StatusPill extends StatelessWidget {
  final String label;
  final Color color;
  final Color background;
  final IconData? icon;

  const StatusPill({
    super.key,
    required this.label,
    required this.color,
    required this.background,
    this.icon,
  });

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: AppDurations.medium,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(AppRadii.pill),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 13, color: color),
            const SizedBox(width: 6),
          ],
          Text(
            label,
            style: TextStyle(
              color: color,
              fontSize: 11,
              fontWeight: FontWeight.w800,
              letterSpacing: 0.6,
            ),
          ),
        ],
      ),
    );
  }
}
