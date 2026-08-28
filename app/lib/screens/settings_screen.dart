import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:record/record.dart';

import '../services/api_service.dart';
import '../services/session_service.dart';
import '../theme/app_theme.dart';
import '../widgets/animations.dart';

class SettingsScreen extends StatefulWidget {
  final double sensitivityThreshold;
  final ValueChanged<double> onSensitivityChanged;

  const SettingsScreen({
    super.key,
    required this.sensitivityThreshold,
    required this.onSensitivityChanged,
  });

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final AudioRecorder _recorder = AudioRecorder();
  final ApiService _api = ApiService();

  String _micStatus = 'Checking…';
  String _locationStatus = 'Checking…';
  Map<String, dynamic>? _escalationStatus;
  List<Map<String, dynamic>> _profiles = const [];

  @override
  void initState() {
    super.initState();
    _refreshPermissionStatus();
    _loadBackendStatus();
  }

  @override
  void dispose() {
    _recorder.dispose();
    super.dispose();
  }

  Future<void> _loadBackendStatus() async {
    final results = await Future.wait([_api.escalationStatus(), _api.getProfiles()]);
    if (!mounted) return;
    setState(() {
      _escalationStatus = results[0] as Map<String, dynamic>?;
      final profiles = (results[1] as Map<String, dynamic>?)?['profiles'];
      _profiles = List<Map<String, dynamic>>.from(profiles as Iterable? ?? const []);
    });
  }

  Future<void> _refreshPermissionStatus() async {
    final hasMic = await _recorder.hasPermission();
    final locationPermission = await Geolocator.checkPermission();
    if (!mounted) return;
    setState(() {
      _micStatus = hasMic ? 'Authorized' : 'Not granted';
      _locationStatus = switch (locationPermission) {
        LocationPermission.always || LocationPermission.whileInUse => 'Authorized',
        LocationPermission.denied => 'Not requested',
        LocationPermission.deniedForever => 'Denied — enable in system settings',
        LocationPermission.unableToDetermine => 'Unavailable',
      };
    });
  }

  Future<void> _requestLocationPermission() async {
    final serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      if (!mounted) return;
      setState(() => _locationStatus = 'Location services are off on this device');
      return;
    }
    await Geolocator.requestPermission();
    await _refreshPermissionStatus();
  }

  double _thresholdForSlider(double sliderValue) {
    // Mirrors the browser prototype: 1 is least sensitive (0.70), 9 is most (0.30).
    return double.parse((0.75 - sliderValue * 0.05).toStringAsFixed(2));
  }

  double _sliderForThreshold(double threshold) =>
      ((0.75 - threshold) / 0.05).clamp(1.0, 9.0);

  String _sensitivityLabel(double sliderValue, double threshold) {
    if (sliderValue < 4) return 'Low (${threshold.toStringAsFixed(2)})';
    if (sliderValue > 7) return 'High (${threshold.toStringAsFixed(2)})';
    return 'Medium (${threshold.toStringAsFixed(2)})';
  }

  @override
  Widget build(BuildContext context) {
    final sliderValue = _sliderForThreshold(widget.sensitivityThreshold);
    final session = AppSession.instance;

    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
        children: [
          FadeSlideIn(index: 0, child: _buildAccountCard(session)),
          const SizedBox(height: 24),
          const FadeSlideIn(index: 1, child: SectionLabel('Detection model')),
          FadeSlideIn(index: 1, child: _buildProfileCard(session)),
          const SizedBox(height: 24),
          const FadeSlideIn(index: 2, child: SectionLabel('Emergency escalation')),
          FadeSlideIn(index: 2, child: _buildEscalationCard(session)),
          const SizedBox(height: 24),
          const FadeSlideIn(index: 3, child: SectionLabel('Detection sensitivity')),
          FadeSlideIn(
            index: 3,
            child: AppCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Pass 1 candidate threshold',
                      style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                  const SizedBox(height: 4),
                  Text(
                    _sensitivityLabel(sliderValue, widget.sensitivityThreshold),
                    style: const TextStyle(fontSize: 12, color: AppColors.inkMuted),
                  ),
                  Slider(
                    value: sliderValue,
                    min: 1,
                    max: 9,
                    divisions: 8,
                    onChanged: (value) => widget.onSensitivityChanged(_thresholdForSlider(value)),
                  ),
                  const Text(
                    'Higher sensitivity catches more events and produces more false candidates; '
                    'pass 2 still has to verify anything before it can alert anyone.',
                    style: TextStyle(fontSize: 11, color: AppColors.inkMuted, height: 1.5),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 24),
          const FadeSlideIn(index: 4, child: SectionLabel('Privacy & permissions')),
          FadeSlideIn(
            index: 4,
            child: AppCard(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
              child: Column(
                children: [
                  _permissionTile('Microphone', _micStatus, null),
                  const Divider(indent: 12, endIndent: 12),
                  _permissionTile(
                    'Location',
                    _locationStatus,
                    _locationStatus == 'Authorized' ? null : _requestLocationPermission,
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 24),
          const FadeSlideIn(index: 5, child: SectionLabel('About')),
          FadeSlideIn(
            index: 5,
            child: AppCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Model engine', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
                  const SizedBox(height: 4),
                  const Text(
                    'FastAPI backend running a fine-tuned YAMNet head (TensorFlow). On-device '
                    'TFLite inference is not yet wired into this app build.',
                    style: TextStyle(fontSize: 12, color: AppColors.inkMuted, height: 1.5),
                  ),
                  const SizedBox(height: 12),
                  const Text('Backend', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
                  const SizedBox(height: 4),
                  Text(
                    AppSession.apiBaseUrl,
                    style: const TextStyle(fontSize: 12, color: AppColors.inkMuted),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildAccountCard(AppSession session) {
    final user = session.currentUser;
    return AppCard(
      child: Row(
        children: [
          Container(
            width: 48,
            height: 48,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: AppColors.primarySoft,
              borderRadius: BorderRadius.circular(14),
            ),
            child: Text(
              (user?.displayName.isNotEmpty == true ? user!.displayName[0] : 'E').toUpperCase(),
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
                Text(
                  user?.displayName ?? 'Echo user',
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 2),
                Text(
                  user?.email ?? '',
                  style: const TextStyle(fontSize: 12, color: AppColors.inkMuted),
                ),
                const SizedBox(height: 2),
                Text(
                  'Local profile · id ${session.userId}',
                  style: const TextStyle(fontSize: 11, color: AppColors.inkFaint),
                ),
              ],
            ),
          ),
          TextButton(
            onPressed: () async {
              await session.signOut();
              if (context.mounted) Navigator.pop(context);
            },
            child: const Text('Sign out'),
          ),
        ],
      ),
    );
  }

  Widget _buildProfileCard(AppSession session) {
    return ValueListenableBuilder<String>(
      valueListenable: session.modelProfile,
      builder: (context, active, _) {
        return AppCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              ..._profileOptions().map((entry) {
                final name = entry['name']?.toString() ?? 'real';
                final loaded = entry['loaded'] != false;
                final selected = active == name;
                return Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: InkWell(
                    borderRadius: BorderRadius.circular(AppRadii.control),
                    onTap: loaded ? () => session.setModelProfile(name) : null,
                    child: AnimatedContainer(
                      duration: AppDurations.medium,
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: selected ? AppColors.primarySoft : AppColors.surfaceAlt,
                        borderRadius: BorderRadius.circular(AppRadii.control),
                        border: Border.all(
                          color: selected ? AppColors.primary : AppColors.line,
                          width: selected ? 1.6 : 1,
                        ),
                      ),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Icon(
                            selected ? Icons.radio_button_checked : Icons.radio_button_off,
                            size: 20,
                            color: selected ? AppColors.primary : AppColors.inkFaint,
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    Text(
                                      name == 'demo' ? 'Demo head (firecracker)' : 'Production head',
                                      style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w800),
                                    ),
                                    const SizedBox(width: 8),
                                    if (!loaded)
                                      const StatusPill(
                                        label: 'NOT BUILT',
                                        color: AppColors.warning,
                                        background: AppColors.warningSoft,
                                      ),
                                  ],
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  entry['description']?.toString() ??
                                      'Eight-class hazard classifier.',
                                  style: const TextStyle(
                                    fontSize: 11,
                                    color: AppColors.inkMuted,
                                    height: 1.5,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                );
              }),
              if (active == 'demo')
                const Text(
                  'Demo head active: firecracker audio is reported as a gunshot so the whole '
                  'alert path can be shown live. Every alert, log line, and message it produces '
                  'is stamped DEMO and keeps the raw firecracker class.',
                  style: TextStyle(fontSize: 11, color: AppColors.warning, height: 1.5),
                ),
            ],
          ),
        );
      },
    );
  }

  List<Map<String, dynamic>> _profileOptions() {
    if (_profiles.isNotEmpty) return _profiles;
    // Backend unreachable: still let the user switch, and say the state is unknown.
    return const [
      {'name': 'real', 'description': 'Eight-class hazard classifier.', 'loaded': true},
      {
        'name': 'demo',
        'description': 'Adds a firecracker class, aliased to gunshot for the demonstration.',
        'loaded': true,
      },
    ];
  }

  Widget _buildEscalationCard(AppSession session) {
    final status = _escalationStatus;
    final telegramOn = status?['telegram_configured'] == true;
    final voiceOn = status?['voice_call_configured'] == true;
    final window = (status?['cancel_window_seconds'] as num?)?.toStringAsFixed(0) ?? '12';
    final minRisk = (status?['min_risk_score'] as num?)?.toStringAsFixed(0) ?? '61';

    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ValueListenableBuilder<bool>(
            valueListenable: session.autoEscalation,
            builder: (context, enabled, _) => SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text(
                'Alert my contacts automatically',
                style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
              ),
              subtitle: Text(
                'Verified high-risk sounds call and message your contacts after a '
                '$window-second window in which you can cancel.',
                style: const TextStyle(fontSize: 12, color: AppColors.inkMuted, height: 1.4),
              ),
              value: enabled,
              onChanged: session.setAutoEscalation,
            ),
          ),
          const Divider(),
          const SizedBox(height: 8),
          _channelRow('Telegram (clip + location)', telegramOn),
          const SizedBox(height: 8),
          _channelRow('Automated voice call', voiceOn),
          const SizedBox(height: 12),
          Text(
            'Escalation floor: risk $minRisk+. Emergency services are never dialled '
            'automatically — the 112 button stays under your control.',
            style: const TextStyle(fontSize: 11, color: AppColors.inkMuted, height: 1.5),
          ),
        ],
      ),
    );
  }

  Widget _channelRow(String label, bool configured) {
    return Row(
      children: [
        Icon(
          configured ? Icons.check_circle : Icons.info_outline,
          size: 18,
          color: configured ? AppColors.success : AppColors.info,
        ),
        const SizedBox(width: 10),
        Expanded(child: Text(label, style: const TextStyle(fontSize: 13))),
        StatusPill(
          label: configured ? 'LIVE' : 'SIMULATED',
          color: configured ? AppColors.success : AppColors.info,
          background: configured ? AppColors.successSoft : AppColors.infoSoft,
        ),
      ],
    );
  }

  Widget _permissionTile(String title, String status, VoidCallback? onTap) {
    final ok = status == 'Authorized';
    return ListTile(
      title: Text(title, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
      subtitle: Text(status, style: const TextStyle(fontSize: 12, color: AppColors.inkMuted)),
      trailing: Icon(
        ok ? Icons.check_circle : Icons.error_outline,
        color: ok ? AppColors.success : AppColors.warning,
        size: 20,
      ),
      onTap: onTap,
    );
  }
}
