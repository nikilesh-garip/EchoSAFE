import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../services/session_service.dart';
import '../theme/app_theme.dart';
import '../widgets/animations.dart';

/// Two records, deliberately kept apart:
///   * Detections -- everything the model verified, including events that were
///     logged but never escalated.
///   * Escalations -- what actually reached another human being, per channel.
/// Collapsing them into one list would hide the difference between "Echo
/// noticed something" and "somebody was called".
class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> with SingleTickerProviderStateMixin {
  final ApiService _api = ApiService();
  late final TabController _tabs = TabController(length: 2, vsync: this);

  bool _loading = true;
  String? _error;
  List<Map<String, dynamic>> _events = const [];
  List<Map<String, dynamic>> _incidents = const [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    final userId = AppSession.instance.userId;
    final results = await Future.wait([
      _api.getEventHistory(userId),
      _api.getIncidentHistory(userId),
    ]);
    if (!mounted) return;
    final events = results[0] as List<Map<String, dynamic>>?;
    final incidents = results[1] as List<Map<String, dynamic>>?;
    setState(() {
      _loading = false;
      if (events == null && incidents == null) {
        _error = 'Could not reach the backend at ${AppSession.apiBaseUrl}.';
      }
      _events = events ?? const [];
      _incidents = incidents ?? const [];
    });
  }

  Future<void> _clearEvents() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Clear detection history?'),
        content: const Text(
          'This deletes the logged detections for this account. Escalation records '
          'are kept — what was sent to other people is not erasable from here.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Clear', style: TextStyle(color: AppColors.danger)),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    await _api.clearEventHistory(AppSession.instance.userId);
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
          child: Row(
            children: [
              const Expanded(
                child: Text('History', style: TextStyle(fontSize: 24, fontWeight: FontWeight.w800)),
              ),
              IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
              IconButton(
                icon: const Icon(Icons.delete_outline, color: AppColors.danger),
                onPressed: _clearEvents,
              ),
            ],
          ),
        ),
        TabBar(
          controller: _tabs,
          labelColor: AppColors.primary,
          unselectedLabelColor: AppColors.inkMuted,
          indicatorColor: AppColors.primary,
          indicatorSize: TabBarIndicatorSize.label,
          labelStyle: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
          tabs: [
            Tab(text: 'Detections (${_events.length})'),
            Tab(text: 'Escalations (${_incidents.length})'),
          ],
        ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.all(20),
            child: Text(_error!, style: const TextStyle(color: AppColors.danger, fontSize: 13)),
          ),
        Expanded(
          child: _loading
              ? const Center(child: CircularProgressIndicator(color: AppColors.primary))
              : TabBarView(
                  controller: _tabs,
                  children: [
                    RefreshIndicator(
                      onRefresh: _load,
                      color: AppColors.primary,
                      child: _buildEvents(),
                    ),
                    RefreshIndicator(
                      onRefresh: _load,
                      color: AppColors.primary,
                      child: _buildIncidents(),
                    ),
                  ],
                ),
        ),
      ],
    );
  }

  Widget _buildEvents() {
    if (_events.isEmpty) return _empty('No detections logged yet.');
    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
      itemCount: _events.length,
      itemBuilder: (context, index) {
        final event = _events[index];
        final level = event['risk_level']?.toString() ?? 'NORMAL';
        final color = AppColors.forRiskLevel(level);
        return FadeSlideIn(
          index: index,
          child: Padding(
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
                    child: Icon(Icons.graphic_eq, size: 19, color: color),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          (event['class_name']?.toString() ?? '').replaceAll('_', ' ').toUpperCase(),
                          style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w800),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          '${_formatTime(event['timestamp'])} · '
                          'P1 ${_pct(event['primary_conf'])} · P2 ${_pct(event['verification_conf'])}',
                          style: const TextStyle(fontSize: 11, color: AppColors.inkMuted),
                        ),
                      ],
                    ),
                  ),
                  StatusPill(
                    label: '${event['risk_score'] ?? 0}',
                    color: color,
                    background: AppColors.softForRiskLevel(level),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildIncidents() {
    if (_incidents.isEmpty) {
      return _empty('No contact escalations yet. Nobody has been called or messaged.');
    }
    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
      itemCount: _incidents.length,
      itemBuilder: (context, index) {
        final incident = _incidents[index];
        final state = incident['state']?.toString() ?? 'UNKNOWN';
        final attempts = List<Map<String, dynamic>>.from(
          incident['attempts'] as Iterable? ?? const [],
        );
        final color = switch (state) {
          'DISPATCHED' => AppColors.danger,
          'CANCELLED' => AppColors.success,
          'PENDING' => AppColors.warning,
          _ => AppColors.inkMuted,
        };

        return FadeSlideIn(
          index: index,
          child: Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: AppCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          (incident['class_name']?.toString() ?? '').replaceAll('_', ' ').toUpperCase(),
                          style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w800),
                        ),
                      ),
                      if (incident['profile'] == 'demo')
                        const Padding(
                          padding: EdgeInsets.only(right: 8),
                          child: StatusPill(
                            label: 'DEMO',
                            color: AppColors.warning,
                            background: AppColors.warningSoft,
                          ),
                        ),
                      StatusPill(
                        label: state,
                        color: color,
                        background: color.withOpacity(0.12),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text(
                    '${_formatTime(incident['created_at'])} · risk ${incident['risk_score'] ?? 0}'
                    '${incident['raw_class'] != null && incident['raw_class'] != incident['class_name'] ? ' · raw ${incident['raw_class']}' : ''}',
                    style: const TextStyle(fontSize: 11, color: AppColors.inkMuted),
                  ),
                  if (incident['note'] != null) ...[
                    const SizedBox(height: 6),
                    Text(
                      incident['note'].toString(),
                      style: const TextStyle(fontSize: 11, color: AppColors.inkMuted, height: 1.4),
                    ),
                  ],
                  if (attempts.isNotEmpty) ...[
                    const SizedBox(height: 10),
                    const Divider(height: 1),
                    const SizedBox(height: 10),
                    ...attempts.map(
                      (attempt) => Padding(
                        padding: const EdgeInsets.only(bottom: 6),
                        child: Row(
                          children: [
                            Icon(
                              attempt['channel'] == 'telegram'
                                  ? Icons.send_outlined
                                  : Icons.phone_in_talk_outlined,
                              size: 15,
                              color: attempt['status'] == 'sent'
                                  ? AppColors.success
                                  : attempt['status'] == 'simulated'
                                      ? AppColors.info
                                      : AppColors.danger,
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                '${attempt['contact_name'] ?? 'Contact'} · ${attempt['status']}',
                                style: const TextStyle(fontSize: 11, color: AppColors.inkMuted),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _empty(String message) {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        const SizedBox(height: 40),
        Icon(Icons.inbox_outlined, size: 42, color: AppColors.inkFaint),
        const SizedBox(height: 12),
        Text(
          message,
          textAlign: TextAlign.center,
          style: const TextStyle(fontSize: 13, color: AppColors.inkMuted, height: 1.5),
        ),
      ],
    );
  }

  String _pct(dynamic value) => '${(((value as num?) ?? 0) * 100).toStringAsFixed(0)}%';

  String _formatTime(dynamic epochSeconds) {
    final time = DateTime.fromMillisecondsSinceEpoch(
      ((((epochSeconds as num?) ?? 0)) * 1000).round(),
    );
    return '${time.day}/${time.month} '
        '${time.hour.toString().padLeft(2, '0')}:${time.minute.toString().padLeft(2, '0')}';
  }
}
