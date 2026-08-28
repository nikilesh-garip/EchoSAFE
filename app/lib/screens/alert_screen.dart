import 'dart:async';

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../services/api_service.dart';
import '../services/session_service.dart';
import '../theme/app_theme.dart';
import '../widgets/animations.dart';
import '../widgets/audio_visualizer.dart';

/// Full-screen alert with the outbound escalation front and centre.
///
/// The old version told the person already standing in the room that
/// something happened. This one shows what is about to be sent to the people
/// who can actually help, gives that person a countdown to stop it, and then
/// reports, per contact and per channel, what really went out.
class AlertScreen extends StatefulWidget {
  final String title;
  final String threatClass;
  final String? rawClass;
  final int riskScore;
  final String riskLevel;
  final double p1Conf;
  final double p2Conf;
  final List<String> instructions;
  final List<Map<String, dynamic>> nearbyFacilities;
  final Map<String, dynamic>? incident;
  final String profile;

  const AlertScreen({
    super.key,
    required this.title,
    required this.threatClass,
    required this.riskScore,
    required this.riskLevel,
    required this.p1Conf,
    required this.p2Conf,
    required this.instructions,
    required this.nearbyFacilities,
    this.rawClass,
    this.incident,
    this.profile = 'real',
  });

  @override
  State<AlertScreen> createState() => _AlertScreenState();
}

class _AlertScreenState extends State<AlertScreen> {
  final ApiService _api = ApiService();
  Timer? _pollTimer;
  Map<String, dynamic>? _incident;
  bool _busy = false;
  // The cancel window is whatever the backend armed this incident with; the
  // ring needs that as its denominator, so capture it the first time we see it.
  double _countdownTotal = 0;

  @override
  void initState() {
    super.initState();
    _incident = widget.incident;
    _countdownTotal = ((_incident?['seconds_to_dispatch'] as num?) ?? 0).toDouble();
    if (_incident?['state'] == 'PENDING') {
      _pollTimer = Timer.periodic(const Duration(milliseconds: 900), (_) => _refreshIncident());
    }
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _refreshIncident() async {
    final id = _incident?['id']?.toString();
    if (id == null) return;
    final updated = await _api.getIncident(id);
    if (!mounted || updated == null) return;
    setState(() => _incident = updated);
    if (updated['state'] != 'PENDING') {
      _pollTimer?.cancel();
      _pollTimer = null;
    }
  }

  Future<void> _cancel() async {
    final id = _incident?['id']?.toString();
    if (id == null) return;
    setState(() => _busy = true);
    final response = await _api.cancelIncident(
      incidentId: id,
      userId: AppSession.instance.userId,
    );
    if (!mounted) return;
    setState(() {
      _busy = false;
      if (response?['incident'] != null) {
        _incident = response!['incident'] as Map<String, dynamic>;
      }
    });
    if (response != null && response['cancelled'] != true && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(response['reason']?.toString() ?? 'Could not cancel.')),
      );
    }
  }

  Future<void> _dispatchNow() async {
    final id = _incident?['id']?.toString();
    if (id == null) return;
    setState(() => _busy = true);
    final updated = await _api.dispatchIncidentNow(
      incidentId: id,
      userLabel: AppSession.instance.displayName,
    );
    if (!mounted) return;
    setState(() {
      _busy = false;
      if (updated != null) _incident = updated;
    });
  }

  @override
  Widget build(BuildContext context) {
    final color = AppColors.forRiskLevel(widget.riskLevel);
    return Scaffold(
      backgroundColor: AppColors.canvas,
      body: SafeArea(
        child: Column(
          children: [
            _buildHeader(color),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 20),
                children: [
                  FadeSlideIn(index: 0, child: _buildEscalationCard()),
                  const SizedBox(height: 22),
                  const FadeSlideIn(index: 1, child: SectionLabel('Detection evidence')),
                  FadeSlideIn(index: 1, child: _buildEvidenceCard()),
                  const SizedBox(height: 22),
                  const FadeSlideIn(index: 2, child: SectionLabel('What to do now')),
                  FadeSlideIn(index: 2, child: _buildGuidanceCard()),
                  const SizedBox(height: 22),
                  const FadeSlideIn(index: 3, child: SectionLabel('Nearby public services')),
                  FadeSlideIn(index: 3, child: _buildFacilities()),
                ],
              ),
            ),
            _buildBottomActions(),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(Color color) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(20, 22, 20, 26),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [color, Color.lerp(color, AppColors.ink, 0.35)!],
        ),
        borderRadius: const BorderRadius.only(
          bottomLeft: Radius.circular(28),
          bottomRight: Radius.circular(28),
        ),
      ),
      child: Column(
        children: [
          Row(
            children: [
              const StatusPill(
                label: 'CRITICAL ALERT',
                color: AppColors.danger,
                background: Colors.white,
                icon: Icons.warning_amber_rounded,
              ),
              const Spacer(),
              if (widget.profile == 'demo')
                const StatusPill(
                  label: 'DEMO PROFILE',
                  color: AppColors.warning,
                  background: Colors.white,
                  icon: Icons.science_outlined,
                ),
            ],
          ),
          const SizedBox(height: 16),
          Text(
            widget.threatClass.replaceAll('_', ' ').toUpperCase(),
            style: const TextStyle(
              fontSize: 28,
              fontWeight: FontWeight.w900,
              color: Colors.white,
              letterSpacing: 1.2,
            ),
          ),
          if (widget.rawClass != null && widget.rawClass != widget.threatClass) ...[
            const SizedBox(height: 6),
            Text(
              'Raw acoustic class: ${widget.rawClass}',
              style: const TextStyle(fontSize: 12, color: Colors.white70),
            ),
          ],
          const SizedBox(height: 10),
          Text(
            'Risk ${widget.riskScore}/100 · ${widget.riskLevel.replaceAll('_', ' ')}',
            style: const TextStyle(fontSize: 14, color: Colors.white, fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }

  Widget _buildEscalationCard() {
    final incident = _incident;
    if (incident == null) {
      return AppCard(
        background: AppColors.surfaceAlt,
        child: Row(
          children: const [
            Icon(Icons.notifications_off_outlined, size: 20, color: AppColors.inkMuted),
            SizedBox(width: 12),
            Expanded(
              child: Text(
                'No contact escalation was created for this detection. Check auto-escalation '
                'in Settings and make sure a contact is saved.',
                style: TextStyle(fontSize: 13, color: AppColors.inkMuted, height: 1.5),
              ),
            ),
          ],
        ),
      );
    }

    final state = incident['state']?.toString() ?? 'UNKNOWN';
    final armed = incident['escalation_armed'];
    final gateReason = incident['gate_reason']?.toString();

    switch (state) {
      case 'PENDING':
        return _buildCountdownCard(incident);
      case 'CANCELLED':
        return _buildStateCard(
          icon: Icons.verified_outlined,
          color: AppColors.success,
          background: AppColors.successSoft,
          title: 'Alert cancelled',
          body: 'Nobody was called or messaged. The detection is still recorded in your history.',
        );
      case 'SUPPRESSED':
        return _buildStateCard(
          icon: Icons.filter_alt_outlined,
          color: AppColors.info,
          background: AppColors.infoSoft,
          title: 'Contacts were not alerted',
          body: gateReason ?? 'This detection did not meet the escalation policy.',
        );
      case 'NO_CONTACTS':
        return _buildStateCard(
          icon: Icons.person_off_outlined,
          color: AppColors.danger,
          background: AppColors.dangerSoft,
          title: 'Nobody could be alerted',
          body: 'No emergency contact is saved. Add one on the Contacts tab so this never '
              'happens again.',
        );
      default:
        return _buildDispatchedCard(incident, armed);
    }
  }

  Widget _buildCountdownCard(Map<String, dynamic> incident) {
    final remaining = (incident['seconds_to_dispatch'] as num?)?.toDouble() ?? 0;
    final total = _countdownTotal > 0 ? _countdownTotal : (remaining > 0 ? remaining : 12);
    return AppCard(
      background: AppColors.dangerSoft,
      borderColor: const Color(0xFFFCA5A5),
      child: Column(
        children: [
          const Text(
            'CALLING YOUR EMERGENCY CONTACTS',
            style: TextStyle(
              fontSize: 12,
              letterSpacing: 1.1,
              fontWeight: FontWeight.w800,
              color: AppColors.danger,
            ),
          ),
          const SizedBox(height: 14),
          CountdownRing(remainingSeconds: remaining, totalSeconds: total),
          const SizedBox(height: 14),
          const Text(
            'They will hear an automated call with the 5 seconds Echo recorded, and receive '
            'the same clip plus your location on Telegram.',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 13, color: Color(0xFF7F1D1D), height: 1.5),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: PressableScale(
                  child: ElevatedButton.icon(
                    onPressed: _busy ? null : _cancel,
                    style: ElevatedButton.styleFrom(backgroundColor: AppColors.success),
                    icon: const Icon(Icons.shield_outlined, size: 18),
                    label: const Text("I'M SAFE"),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: PressableScale(
                  child: ElevatedButton.icon(
                    onPressed: _busy ? null : _dispatchNow,
                    style: ElevatedButton.styleFrom(backgroundColor: AppColors.danger),
                    icon: const Icon(Icons.campaign_outlined, size: 18),
                    label: const Text('ALERT NOW'),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildStateCard({
    required IconData icon,
    required Color color,
    required Color background,
    required String title,
    required String body,
  }) {
    return AppCard(
      background: background,
      borderColor: color.withOpacity(0.35),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 22, color: color),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: color)),
                const SizedBox(height: 6),
                Text(body, style: const TextStyle(fontSize: 13, height: 1.5, color: AppColors.ink)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDispatchedCard(Map<String, dynamic> incident, dynamic armed) {
    final attempts = List<Map<String, dynamic>>.from(
      (incident['attempts'] as Iterable?) ?? const [],
    );
    final anySimulated = attempts.any((a) => a['status'] == 'simulated');
    // The backend reverse-geocodes the place label it was given (see
    // backend/geocode.py) once the incident dispatches, so this is only
    // ever a real resolved address -- never a fabricated fallback.
    final placeLabel = incident['place_label']?.toString();

    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.campaign, size: 20, color: AppColors.danger),
              const SizedBox(width: 10),
              const Expanded(
                child: Text(
                  'Contacts alerted',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800),
                ),
              ),
              if (anySimulated)
                const StatusPill(
                  label: 'SIMULATED',
                  color: AppColors.info,
                  background: AppColors.infoSoft,
                ),
            ],
          ),
          const SizedBox(height: 14),
          if (attempts.isEmpty)
            const Text(
              'Dispatching…',
              style: TextStyle(fontSize: 13, color: AppColors.inkMuted),
            ),
          ...attempts.map(_buildAttemptRow),
          if (placeLabel != null && placeLabel.isNotEmpty) ...[
            const SizedBox(height: 4),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.place_outlined, size: 16, color: AppColors.inkMuted),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'Location sent: $placeLabel',
                    style: const TextStyle(fontSize: 11, color: AppColors.inkMuted, height: 1.4),
                  ),
                ),
              ],
            ),
          ],
          if (anySimulated) ...[
            const SizedBox(height: 10),
            const Text(
              'Simulated means the channel is not configured yet, so the message was composed '
              'and logged but not sent. Configure the Telegram bot token and the call provider '
              'in the backend .env to make these real.',
              style: TextStyle(fontSize: 11, color: AppColors.inkMuted, height: 1.5),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildAttemptRow(Map<String, dynamic> attempt) {
    final status = attempt['status']?.toString() ?? 'unknown';
    final channel = attempt['channel']?.toString() ?? 'unknown';
    final color = switch (status) {
      'sent' => AppColors.success,
      'simulated' => AppColors.info,
      _ => AppColors.danger,
    };
    final icon = switch (channel) {
      'telegram' => Icons.send_outlined,
      'voice_call' => Icons.phone_in_talk_outlined,
      _ => Icons.error_outline,
    };

    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 34,
            height: 34,
            decoration: BoxDecoration(
              color: color.withOpacity(0.12),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(icon, size: 17, color: color),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${attempt['contact_name'] ?? 'Contact'} · '
                  '${channel == 'voice_call' ? 'Automated call' : 'Telegram'}',
                  style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: 2),
                Text(
                  attempt['detail']?.toString() ?? status,
                  style: const TextStyle(fontSize: 11, color: AppColors.inkMuted, height: 1.4),
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          StatusPill(
            label: status.toUpperCase(),
            color: color,
            background: color.withOpacity(0.12),
          ),
        ],
      ),
    );
  }

  Widget _buildEvidenceCard() {
    return AppCard(
      child: Row(
        children: [
          RiskGauge(score: widget.riskScore, level: widget.riskLevel, size: 110),
          const SizedBox(width: 18),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _confidenceLine('Pass 1 · primary', widget.p1Conf),
                const SizedBox(height: 12),
                _confidenceLine('Pass 2 · verification', widget.p2Conf),
                const SizedBox(height: 12),
                Text(
                  _incident?['has_clip'] == true
                      ? '5-second evidence clip stored and attached to the alert.'
                      : 'No evidence clip stored for this detection.',
                  style: const TextStyle(fontSize: 11, color: AppColors.inkMuted, height: 1.4),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _confidenceLine(String label, double value) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label, style: const TextStyle(fontSize: 12, color: AppColors.inkMuted)),
            Text(
              '${(value * 100).toStringAsFixed(0)}%',
              style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w800),
            ),
          ],
        ),
        const SizedBox(height: 6),
        ClipRRect(
          borderRadius: BorderRadius.circular(6),
          child: LinearProgressIndicator(
            value: value.clamp(0.0, 1.0),
            minHeight: 6,
            backgroundColor: AppColors.surfaceAlt,
            valueColor: const AlwaysStoppedAnimation(AppColors.primary),
          ),
        ),
      ],
    );
  }

  Widget _buildGuidanceCard() {
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: widget.instructions
            .map(
              (step) => Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.arrow_right_alt, size: 18, color: AppColors.accent),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        step,
                        style: const TextStyle(fontSize: 13, height: 1.5, color: AppColors.ink),
                      ),
                    ),
                  ],
                ),
              ),
            )
            .toList(),
      ),
    );
  }

  Widget _buildFacilities() {
    return Column(
      children: widget.nearbyFacilities
          .map(
            (facility) => Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: AppCard(
                padding: const EdgeInsets.all(14),
                child: Row(
                  children: [
                    const Icon(Icons.place_outlined, size: 18, color: AppColors.primary),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            facility['name']?.toString() ?? 'Unnamed',
                            style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            facility['address']?.toString() ?? '',
                            style: const TextStyle(fontSize: 11, color: AppColors.inkMuted, height: 1.4),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          )
          .toList(),
    );
  }

  Widget _buildBottomActions() {
    return Container(
      padding: const EdgeInsets.fromLTRB(20, 14, 20, 18),
      decoration: BoxDecoration(
        color: AppColors.surface,
        border: const Border(top: BorderSide(color: AppColors.line)),
        boxShadow: softShadow(opacity: 0.06, blur: 20, y: -6),
      ),
      child: Row(
        children: [
          Expanded(
            child: PressableScale(
              child: ElevatedButton.icon(
                style: ElevatedButton.styleFrom(backgroundColor: AppColors.danger),
                onPressed: () async {
                  // User-initiated handoff only; Echo never dials emergency
                  // services automatically. See docs/SAFETY_IMPLEMENTATION_PLAN.md.
                  final uri = Uri(scheme: 'tel', path: '112');
                  if (await canLaunchUrl(uri)) {
                    await launchUrl(uri);
                  } else if (context.mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('Could not open the phone dialer on this device.')),
                    );
                  }
                },
                icon: const Icon(Icons.call, size: 18),
                label: const Text('CALL 112'),
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: OutlinedButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('CLOSE'),
            ),
          ),
        ],
      ),
    );
  }
}
