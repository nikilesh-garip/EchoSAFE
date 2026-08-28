import 'package:flutter/material.dart';

import 'screens/contacts_screen.dart';
import 'screens/dashboard_screen.dart';
import 'screens/demo_screen.dart';
import 'screens/history_screen.dart';
import 'screens/live_monitor_screen.dart';
import 'screens/login_screen.dart';
import 'services/motion_service.dart';
import 'services/session_service.dart';
import 'theme/app_theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const EchoApp());
}

class EchoApp extends StatefulWidget {
  const EchoApp({super.key});

  @override
  State<EchoApp> createState() => _EchoAppState();
}

class _EchoAppState extends State<EchoApp> {
  @override
  void initState() {
    super.initState();
    AppSession.instance.restore();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'ECHO',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      home: ValueListenableBuilder<bool>(
        valueListenable: AppSession.instance.restoring,
        builder: (context, restoring, _) {
          if (restoring) {
            return const Scaffold(
              backgroundColor: AppColors.canvas,
              body: Center(child: CircularProgressIndicator(color: AppColors.primary)),
            );
          }
          return ValueListenableBuilder<SessionUser?>(
            valueListenable: AppSession.instance.user,
            builder: (context, user, _) => AnimatedSwitcher(
              duration: AppDurations.slow,
              switchInCurve: Curves.easeOutCubic,
              child: user == null
                  ? const LoginScreen(key: ValueKey('login'))
                  : const MainNavigationShell(key: ValueKey('shell')),
            ),
          );
        },
      ),
    );
  }
}

class MainNavigationShell extends StatefulWidget {
  const MainNavigationShell({super.key});

  @override
  State<MainNavigationShell> createState() => _MainNavigationShellState();
}

class _MainNavigationShellState extends State<MainNavigationShell> {
  int _currentIndex = 0;

  // Context signals shared between Dashboard (toggles), Live Monitor (reads
  // them before every /detect call), and Settings (sensitivity slider) so the
  // UI can never show a toggle that silently does nothing.
  bool _mediaPlayback = false;
  bool _suddenMotion = false;
  double _sensitivityThreshold = 0.50;
  bool _isMonitoring = false;

  // Accelerometer-backed auto-detector for sudden motion (a jolt, fall, or
  // sprint start). It only ever ADDS evidence on top of the manual "Sudden
  // motion (panic)" toggle above -- see MotionService's doc comment for the
  // same "automatic signal never overrides an explicit False" philosophy the
  // backend already uses for acoustic media-context detection. The OR with
  // `_suddenMotion` is computed in `_buildScreens` below, right where the
  // combined value is actually sent, so `_suddenMotion` itself keeps meaning
  // exactly what the manual toggle reports.
  final MotionService _motionService = MotionService();

  @override
  void initState() {
    super.initState();
    _motionService.start();
    // Screens are only rebuilt on setState, so the auto-detected flag needs
    // to trigger one whenever it changes -- both when a jolt fires and when
    // it decays back to false a few seconds later.
    _motionService.detected.addListener(_onAutoMotionChanged);
  }

  void _onAutoMotionChanged() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _motionService.detected.removeListener(_onAutoMotionChanged);
    _motionService.dispose();
    super.dispose();
  }

  void _goToMonitorTab() => setState(() => _currentIndex = 1);

  List<Widget> _buildScreens() {
    final autoMotionDetected = _motionService.detected.value;
    final effectiveSuddenMotion = _suddenMotion || autoMotionDetected;
    return [
      DashboardScreen(
        isMonitoring: _isMonitoring,
        mediaPlayback: _mediaPlayback,
        suddenMotion: _suddenMotion,
        autoMotionDetected: autoMotionDetected,
        sensitivityThreshold: _sensitivityThreshold,
        onMediaPlaybackChanged: (value) => setState(() => _mediaPlayback = value),
        onSuddenMotionChanged: (value) => setState(() => _suddenMotion = value),
        onSensitivityChanged: (value) => setState(() => _sensitivityThreshold = value),
        onOpenMonitor: _goToMonitorTab,
        onOpenContacts: () => setState(() => _currentIndex = 3),
      ),
      LiveMonitorScreen(
        mediaPlayback: _mediaPlayback,
        suddenMotion: effectiveSuddenMotion,
        sensitivityThreshold: _sensitivityThreshold,
        onMonitoringChanged: (value) => setState(() => _isMonitoring = value),
      ),
      const HistoryScreen(),
      const ContactsScreen(),
      DemoScreen(
        mediaPlayback: _mediaPlayback,
        suddenMotion: effectiveSuddenMotion,
        sensitivityThreshold: _sensitivityThreshold,
      ),
    ];
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: AnimatedSwitcher(
          duration: AppDurations.medium,
          switchInCurve: Curves.easeOutCubic,
          transitionBuilder: (child, animation) => FadeTransition(
            opacity: animation,
            child: SlideTransition(
              position: Tween<Offset>(begin: const Offset(0, 0.02), end: Offset.zero)
                  .animate(animation),
              child: child,
            ),
          ),
          child: KeyedSubtree(
            key: ValueKey<int>(_currentIndex),
            child: _buildScreens()[_currentIndex],
          ),
        ),
      ),
      bottomNavigationBar: Container(
        decoration: BoxDecoration(
          color: AppColors.surface,
          border: const Border(top: BorderSide(color: AppColors.line)),
          boxShadow: softShadow(opacity: 0.05, blur: 18, y: -4),
        ),
        child: SafeArea(
          top: false,
          child: NavigationBarTheme(
            data: NavigationBarThemeData(
              backgroundColor: Colors.transparent,
              indicatorColor: AppColors.primarySoft,
              labelTextStyle: WidgetStateProperty.resolveWith(
                (states) => TextStyle(
                  fontSize: 11,
                  fontWeight: states.contains(WidgetState.selected)
                      ? FontWeight.w700
                      : FontWeight.w500,
                  color: states.contains(WidgetState.selected)
                      ? AppColors.primary
                      : AppColors.inkMuted,
                ),
              ),
              iconTheme: WidgetStateProperty.resolveWith(
                (states) => IconThemeData(
                  size: 22,
                  color: states.contains(WidgetState.selected)
                      ? AppColors.primary
                      : AppColors.inkMuted,
                ),
              ),
            ),
            child: NavigationBar(
              height: 66,
              elevation: 0,
              selectedIndex: _currentIndex,
              onDestinationSelected: (index) => setState(() => _currentIndex = index),
              destinations: [
                const NavigationDestination(
                  icon: Icon(Icons.dashboard_outlined),
                  selectedIcon: Icon(Icons.dashboard),
                  label: 'Dashboard',
                ),
                NavigationDestination(
                  icon: Stack(
                    clipBehavior: Clip.none,
                    children: [
                      const Icon(Icons.graphic_eq_outlined),
                      if (_isMonitoring)
                        Positioned(
                          right: -2,
                          top: -2,
                          child: Container(
                            width: 8,
                            height: 8,
                            decoration: const BoxDecoration(
                              color: AppColors.success,
                              shape: BoxShape.circle,
                            ),
                          ),
                        ),
                    ],
                  ),
                  selectedIcon: const Icon(Icons.graphic_eq),
                  label: 'Monitor',
                ),
                const NavigationDestination(
                  icon: Icon(Icons.history_outlined),
                  selectedIcon: Icon(Icons.history),
                  label: 'History',
                ),
                const NavigationDestination(
                  icon: Icon(Icons.contacts_outlined),
                  selectedIcon: Icon(Icons.contacts),
                  label: 'Contacts',
                ),
                const NavigationDestination(
                  icon: Icon(Icons.play_circle_outline),
                  selectedIcon: Icon(Icons.play_circle),
                  label: 'Demo',
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
