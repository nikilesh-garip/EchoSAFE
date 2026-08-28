import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../services/session_service.dart';
import '../theme/app_theme.dart';
import '../widgets/animations.dart';
import '../widgets/audio_visualizer.dart';
import 'settings_screen.dart';

/// Home dashboard: status, who would be alerted, context signals, activity.
class DashboardScreen extends StatefulWidget {
  final bool isMonitoring;
  final bool mediaPlayback;
  final bool suddenMotion;
  // Whether MotionService's accelerometer auto-detector has fired within its
  // hold window. This is display-only: it never changes what `suddenMotion`
  // reports, it just tells the user their manual toggle is not the only
  // source of this signal. See MotionService's doc comment.
  final bool autoMotionDetected;
  final double sensitivityThreshold;
  final ValueChanged<bool> onMediaPlaybackChanged;
  final ValueChanged<bool> onSuddenMotionChanged;
  final ValueChanged<double> onSensitivityChanged;
  final VoidCallback onOpenMonitor;
  final VoidCallback onOpenContacts;

  const DashboardScreen({
    super.key,
    required this.isMonitoring,
    required this.mediaPlayback,
    required this.suddenMotion,
    required this.autoMotionDetected,
    required this.sensitivityThreshold,
    required this.onMediaPlaybackChanged,
    required this.onSuddenMotionChanged,
    required this.onSensitivityChanged,
    required this.onOpenMonitor,
    required this.onOpenContacts,
  });

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final ApiService _api = ApiService();

  Map<String, dynamic>? _readiness;
  List<Map<String, dynamic>> _recentEvents = const [];
  bool _loading = true;
  bool _backendReachable = true;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    setState(() => _loading = true);
    final userId = AppSession.instance.userId;
    final results = await Future.wait([
      _api.escalationReadiness(userId),
      _api.getEventHistory(userId),
    ]);
    if (!mounted) return;
    final readiness = results[0] as Map<String, dynamic>?;
    final events = results[1] as List<Map<String, dynamic>>?;
    setState(() {
      _loading = false;
      _backendReachable = readiness != null || events != null;
      _readiness = readiness;
      _recentEvents = (events ?? const []).take(4).toList();
    });
  }

  @override
  Widget build(BuildContext context) {
    final session = AppSession.instance;
    return RefreshIndicator(
      onRefresh: _refresh,
      color: AppColors.primary,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
        children: [
          FadeSlideIn(index: 0, child: _buildHeader(session)),
          const SizedBox(height: 20),
          FadeSlideIn(index: 1, child: _buildHero()),
          if (!_backendReachable && !_loading) ...[
            const SizedBox(height: 14),
            FadeSlideIn(index: 2, child: _buildBackendWarning()),
          ],
          const SizedBox(height: 20),
          FadeSlideIn(index: 2, child: _buildEscalationCard()),
          const SizedBox(height: 24),
          const FadeSlideIn(index: 3, child: SectionLabel('Device context signals')),
          FadeSlideIn(index: 3, child: _buildContextCard()),
          const SizedBox(height: 24),
          FadeSlideIn(
            index: 4,
            child: SectionLabel(
              'Recent detections',
              trailing: TextButton(
                onPressed: _refresh,
                child: const Text('Refresh', style: TextStyle(fontSize: 12)),
              ),
            ),
          ),
          FadeSlideIn(index: 4, child: _buildRecentEvents()),
        ],
      ),
    );
  }

  Widget _buildHeader(AppSession session) {
    final name = session.displayName;
    return Row(
      children: [
        Container(
          width: 46,
          height: 46,
          decoration: BoxDecoration(
            color: AppColors.primarySoft,
            borderRadius: BorderRadius.circular(14),
          ),
          alignment: Alignment.center,
          child: Text(
            name.isNotEmpty ? name[0].toUpperCase() : 'E',
            style: const TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.w800,
              color: AppColors.primary,
            ),
          ),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'ECHO SHIELD',
                style: TextStyle(
                  fontSize: 11,
                  letterSpacing: 1.6,
                  fontWeight: FontWeight.w800,
                  color: AppColors.inkMuted,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                name,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
              ),
            ],
          ),
        ),
        ValueListenableBuilder<String>(
          valueListenable: session.modelProfile,
          builder: (context, profile, _) => profile == 'demo'
              ? const Padding(
                  padding: EdgeInsets.only(right: 8),
                  child: StatusPill(
                    label: 'DEMO MODEL',
                    color: AppColors.warning,
                    background: AppColors.warningSoft,
                    icon: Icons.science_outlined,
                  ),
                )
              : const SizedBox.shrink(),
        ),
        IconButton(
          icon: const Icon(Icons.settings_outlined),
          onPressed: () => Navigator.push(
            context,
            MaterialPageRoute(
              builder: (context) => SettingsScreen(
                sensitivityThreshold: widget.sensitivityThreshold,
                onSensitivityChanged: widget.onSensitivityChanged,
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildHero() {
    final monitoring = widget.isMonitoring;
    return AppCard(
      padding: const EdgeInsets.fromLTRB(20, 24, 20, 20),
      child: Column(
        children: [
          PulseRing(
            active: monitoring,
            color: monitoring ? AppColors.primary : AppColors.inkFaint,
            size: 158,
            child: Container(
              width: 84,
              height: 84,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: monitoring ? AppColors.primarySoft : AppColors.surfaceAlt,
              ),
              child: Icon(
                monitoring ? Icons.hearing : Icons.hearing_disabled,
                size: 36,
                color: monitoring ? AppColors.primary : AppColors.inkFaint,
              ),
            ),
          ),
          const SizedBox(height: 16),
          StatusPill(
            label: monitoring ? 'LISTENING' : 'STANDBY',
            color: monitoring ? AppColors.success : AppColors.inkMuted,
            background: monitoring ? AppColors.successSoft : AppColors.surfaceAlt,
            icon: monitoring ? Icons.circle : Icons.pause_circle_outline,
          ),
          const SizedBox(height: 12),
          Text(
            monitoring
                ? 'Echo is analysing 2-second windows and verifying anything suspicious over 5 seconds.'
                : 'Monitoring runs on the Live Monitor tab, where the microphone session lives.',
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 13, color: AppColors.inkMuted, height: 1.5),
          ),
          const SizedBox(height: 18),
          PressableScale(
            child: ElevatedButton.icon(
              onPressed: widget.onOpenMonitor,
              icon: Icon(monitoring ? Icons.open_in_full : Icons.play_arrow_rounded),
              label: Text(monitoring ? 'VIEW LIVE MONITOR' : 'OPEN LIVE MONITOR'),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBackendWarning() {
    return AppCard(
      background: AppColors.warningSoft,
      borderColor: const Color(0xFFFDE68A),
      padding: const EdgeInsets.all(16),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.cloud_off_outlined, size: 18, color: AppColors.warning),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              'Backend unreachable at ${AppSession.apiBaseUrl}. Detection and alerts will not '
              'work until it is running.',
              style: const TextStyle(fontSize: 12, height: 1.5, color: Color(0xFF92400E)),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildEscalationCard() {
    final readiness = _readiness;
    final ready = readiness?['ready'] == true;
    final contactCount = (readiness?['contact_count'] as num?)?.toInt() ?? 0;
    final blockers = List<String>.from(readiness?['blockers'] as Iterable? ?? const []);
    final channels = readiness?['channels'] as Map<String, dynamic>?;
    final simulated = channels?['simulation_mode'] == true;

    return AppCard(
      onTap: widget.onOpenContacts,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                ready ? Icons.verified_user_outlined : Icons.gpp_maybe_outlined,
                size: 20,
                color: ready ? AppColors.success : AppColors.warning,
              ),
              const SizedBox(width: 10),
              const Expanded(
                child: Text(
                  'If something happens now',
                  style: TextStyle(fontSize: 15, fontWeight: FontWeight.w800),
                ),
              ),
              StatusPill(
                label: _loading ? 'CHECKING' : (ready ? 'READY' : 'INCOMPLETE'),
                color: ready ? AppColors.success : AppColors.warning,
                background: ready ? AppColors.successSoft : AppColors.warningSoft,
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            contactCount == 0
                ? 'No emergency contact is saved yet, so nobody would be called or messaged.'
                : '$contactCount contact${contactCount == 1 ? '' : 's'} would be called with an '
                    'automated voice alert and sent the 5-second clip plus your location on Telegram.',
            style: const TextStyle(fontSize: 13, color: AppColors.inkMuted, height: 1.5),
          ),
          if (simulated) ...[
            const SizedBox(height: 10),
            const StatusPill(
              label: 'SIMULATION MODE',
              color: AppColors.info,
              background: AppColors.infoSoft,
              icon: Icons.science_outlined,
            ),
          ],
          if (blockers.isNotEmpty) ...[
            const SizedBox(height: 12),
            ...blockers.take(3).map(
                  (blocker) => Padding(
                    padding: const EdgeInsets.only(bottom: 6),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Icon(Icons.chevron_right, size: 16, color: AppColors.inkFaint),
                        Expanded(
                          child: Text(
                            blocker,
                            style: const TextStyle(fontSize: 12, color: AppColors.inkMuted, height: 1.4),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
          ],
          const SizedBox(height: 8),
          Row(
            children: const [
              Text(
                'Manage contacts',
                style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: AppColors.primary),
              ),
              SizedBox(width: 4),
              Icon(Icons.arrow_forward, size: 15, color: AppColors.primary),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildContextCard() {
    return AppCard(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      child: Column(
        children: [
          SwitchListTile(
            contentPadding: const EdgeInsets.symmetric(horizontal: 12),
            title: const Text('Media audio active', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
            subtitle: const Text(
              'Lowers risk so TV and movie sounds do not raise an alarm',
              style: TextStyle(fontSize: 12, color: AppColors.inkMuted),
            ),
            value: widget.mediaPlayback,
            onChanged: widget.onMediaPlaybackChanged,
          ),
          const Divider(indent: 12, endIndent: 12),
          SwitchListTile(
            contentPadding: const EdgeInsets.symmetric(horizontal: 12),
            title: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Flexible(
                  child: Text(
                    'Sudden motion (panic)',
                    style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
                  ),
                ),
                // Shown while the accelerometer auto-detector has fired
                // recently, so the toggle does not read as the only source
                // of this signal (it never flips the switch itself).
                if (widget.autoMotionDetected) ...[
                  const SizedBox(width: 8),
                  const StatusPill(
                    label: 'AUTO-DETECTED',
                    color: AppColors.info,
                    background: AppColors.infoSoft,
                    icon: Icons.vibration,
                  ),
                ],
              ],
            ),
            subtitle: const Text(
              'Raises risk when running or a sharp movement is reported',
              style: TextStyle(fontSize: 12, color: AppColors.inkMuted),
            ),
            value: widget.suddenMotion,
            onChanged: widget.onSuddenMotionChanged,
          ),
        ],
      ),
    );
  }

  Widget _buildRecentEvents() {
    if (_loading) {
      return const AppCard(
        child: Center(
          child: Padding(
            padding: EdgeInsets.all(16),
            child: CircularProgressIndicator(color: AppColors.primary),
          ),
        ),
      );
    }
    if (_recentEvents.isEmpty) {
      return const AppCard(
        child: Row(
          children: [
            Icon(Icons.check_circle_outline, color: AppColors.success, size: 20),
            SizedBox(width: 12),
            Expanded(
              child: Text(
                'No detections recorded yet.',
                style: TextStyle(fontSize: 13, color: AppColors.inkMuted),
              ),
            ),
          ],
        ),
      );
    }

    return Column(
      children: _recentEvents.map((event) {
        final level = event['risk_level']?.toString() ?? 'NORMAL';
        final color = AppColors.forRiskLevel(level);
        final timestamp = DateTime.fromMillisecondsSinceEpoch(
          (((event['timestamp'] as num?) ?? 0) * 1000).round(),
        );
        return Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: AppCard(
            padding: const EdgeInsets.all(14),
            child: Row(
              children: [
                Container(
                  width: 42,
                  height: 42,
                  decoration: BoxDecoration(
                    color: AppColors.softForRiskLevel(level),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Icon(Icons.warning_amber_rounded, size: 20, color: color),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        (event['class_name']?.toString() ?? 'unknown').replaceAll('_', ' ').toUpperCase(),
                        style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w800),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        '${timestamp.day}/${timestamp.month} '
                        '${timestamp.hour.toString().padLeft(2, '0')}:'
                        '${timestamp.minute.toString().padLeft(2, '0')}',
                        style: const TextStyle(fontSize: 11, color: AppColors.inkMuted),
                      ),
                    ],
                  ),
                ),
                AnimatedCounter(
                  value: (event['risk_score'] as num?)?.toInt() ?? 0,
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: color),
                ),
              ],
            ),
          ),
        );
      }).toList(),
    );
  }
}
