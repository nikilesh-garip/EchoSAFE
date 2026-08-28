import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../services/session_service.dart';
import '../theme/app_theme.dart';
import '../widgets/animations.dart';

/// Emergency contacts and how each one is reached.
///
/// A contact row is now a routing rule, not just a phone number: escalation
/// order, the Telegram chat that receives the clip and location, and a
/// per-channel opt-out. The rehearsal button at the top exists because setup
/// that is only ever exercised during a real emergency is setup that does not
/// work.
class ContactsScreen extends StatefulWidget {
  const ContactsScreen({super.key});

  @override
  State<ContactsScreen> createState() => _ContactsScreenState();
}

class _ContactsScreenState extends State<ContactsScreen> {
  final ApiService _api = ApiService();

  bool _loading = true;
  bool _busy = false;
  String? _error;
  String? _notice;
  List<Map<String, dynamic>> _contacts = const [];
  Map<String, dynamic>? _readiness;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    final userId = AppSession.instance.userId;
    final results = await Future.wait([
      _api.getContacts(userId),
      _api.escalationReadiness(userId),
    ]);
    if (!mounted) return;
    final contacts = results[0] as List<Map<String, dynamic>>?;
    setState(() {
      _loading = false;
      _readiness = results[1] as Map<String, dynamic>?;
      if (contacts == null) {
        _error = 'Could not reach the backend at ${AppSession.apiBaseUrl}.';
      } else {
        _contacts = contacts;
      }
    });
  }

  Future<void> _delete(int contactId) async {
    final ok = await _api.deleteContact(contactId, userId: AppSession.instance.userId);
    if (!mounted) return;
    if (ok) {
      await _load();
    } else {
      setState(() => _error = 'Could not delete the contact.');
    }
  }

  Future<void> _toggleChannel(Map<String, dynamic> contact, String field, bool value) async {
    final updated = await _api.updateContact(
      contactId: contact['id'] as int,
      userId: AppSession.instance.userId,
      fields: {field: value},
    );
    if (!mounted) return;
    if (updated == null) {
      setState(() => _error = 'Could not update that contact.');
    } else {
      await _load();
    }
  }

  Future<void> _runTest() async {
    setState(() {
      _busy = true;
      _notice = null;
      _error = null;
    });
    final result = await _api.sendEscalationTest(
      userId: AppSession.instance.userId,
      userLabel: AppSession.instance.displayName,
    );
    if (!mounted) return;
    setState(() => _busy = false);
    if (result == null) {
      setState(() => _error = 'Test failed. Add a contact first and make sure the backend is running.');
      return;
    }
    final attempts = List<Map<String, dynamic>>.from(result['attempts'] as Iterable? ?? const []);
    final sent = attempts.where((a) => a['status'] == 'sent').length;
    final simulated = attempts.where((a) => a['status'] == 'simulated').length;
    final failed = attempts.where((a) => a['status'] == 'failed').length;
    setState(() => _notice =
        'Rehearsal complete — $sent delivered, $simulated simulated, $failed failed.');
    if (mounted) _showAttempts(attempts);
  }

  void _showAttempts(List<Map<String, dynamic>> attempts) {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (context) => Padding(
        padding: const EdgeInsets.fromLTRB(20, 20, 20, 32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Rehearsal result', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
            const SizedBox(height: 4),
            const Text(
              'Exactly what each channel did. "Simulated" means the channel is not '
              'configured yet in the backend .env.',
              style: TextStyle(fontSize: 12, color: AppColors.inkMuted, height: 1.5),
            ),
            const SizedBox(height: 16),
            ...attempts.map(
              (attempt) => Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(
                      attempt['channel'] == 'telegram'
                          ? Icons.send_outlined
                          : Icons.phone_in_talk_outlined,
                      size: 18,
                      color: attempt['status'] == 'sent'
                          ? AppColors.success
                          : attempt['status'] == 'simulated'
                              ? AppColors.info
                              : AppColors.danger,
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '${attempt['contact_name'] ?? 'Contact'} · ${attempt['status']}',
                            style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            attempt['detail']?.toString() ?? '',
                            style: const TextStyle(fontSize: 11, color: AppColors.inkMuted, height: 1.4),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _openEditor({Map<String, dynamic>? existing}) async {
    final saved = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => _ContactEditor(api: _api, existing: existing),
    );
    if (saved == true) await _load();
  }

  @override
  Widget build(BuildContext context) {
    final ready = _readiness?['ready'] == true;
    return Stack(
      children: [
        RefreshIndicator(
          onRefresh: _load,
          color: AppColors.primary,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 100),
            children: [
              FadeSlideIn(
                index: 0,
                child: Row(
                  children: [
                    const Expanded(
                      child: Text(
                        'Emergency contacts',
                        style: TextStyle(fontSize: 24, fontWeight: FontWeight.w800),
                      ),
                    ),
                    StatusPill(
                      label: ready ? 'READY' : 'INCOMPLETE',
                      color: ready ? AppColors.success : AppColors.warning,
                      background: ready ? AppColors.successSoft : AppColors.warningSoft,
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 6),
              const FadeSlideIn(
                index: 0,
                child: Text(
                  'These people are called and messaged when Echo verifies a high-risk sound. '
                  'They are contacted in the order shown.',
                  style: TextStyle(fontSize: 13, color: AppColors.inkMuted, height: 1.5),
                ),
              ),
              const SizedBox(height: 16),
              FadeSlideIn(
                index: 1,
                child: AppCard(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Text(
                        'Test the whole chain',
                        style: TextStyle(fontSize: 15, fontWeight: FontWeight.w800),
                      ),
                      const SizedBox(height: 4),
                      const Text(
                        'Sends a clearly-labelled rehearsal call and Telegram message to every '
                        'contact, and reports exactly what each channel did.',
                        style: TextStyle(fontSize: 12, color: AppColors.inkMuted, height: 1.5),
                      ),
                      const SizedBox(height: 14),
                      OutlinedButton.icon(
                        onPressed: _busy || _contacts.isEmpty ? null : _runTest,
                        icon: _busy
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.wifi_tethering, size: 18),
                        label: Text(_busy ? 'SENDING…' : 'RUN ESCALATION REHEARSAL'),
                      ),
                    ],
                  ),
                ),
              ),
              if (_notice != null) ...[
                const SizedBox(height: 12),
                _banner(_notice!, AppColors.successSoft, AppColors.success, Icons.check_circle_outline),
              ],
              if (_error != null) ...[
                const SizedBox(height: 12),
                _banner(_error!, AppColors.dangerSoft, AppColors.danger, Icons.error_outline),
              ],
              const SizedBox(height: 24),
              const SectionLabel('Contact list'),
              if (_loading)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 32),
                  child: Center(child: CircularProgressIndicator(color: AppColors.primary)),
                )
              else if (_contacts.isEmpty)
                const AppCard(
                  child: Text(
                    'No contacts yet. Add the person who should be called if Echo hears '
                    'something dangerous.',
                    style: TextStyle(fontSize: 13, color: AppColors.inkMuted, height: 1.5),
                  ),
                )
              else
                ..._contacts.asMap().entries.map(
                      (entry) => FadeSlideIn(
                        index: entry.key + 2,
                        child: Padding(
                          padding: const EdgeInsets.only(bottom: 12),
                          child: _buildContactCard(entry.value, entry.key),
                        ),
                      ),
                    ),
            ],
          ),
        ),
        Positioned(
          right: 20,
          bottom: 20,
          child: FloatingActionButton.extended(
            backgroundColor: AppColors.primary,
            foregroundColor: Colors.white,
            onPressed: () => _openEditor(),
            icon: const Icon(Icons.person_add_alt),
            label: const Text('ADD CONTACT'),
          ),
        ),
      ],
    );
  }

  Widget _banner(String text, Color background, Color color, IconData icon) {
    return AppCard(
      background: background,
      borderColor: color.withOpacity(0.3),
      padding: const EdgeInsets.all(14),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 18, color: color),
          const SizedBox(width: 10),
          Expanded(
            child: Text(text, style: TextStyle(fontSize: 12, color: color, height: 1.5)),
          ),
        ],
      ),
    );
  }

  Widget _buildContactCard(Map<String, dynamic> contact, int index) {
    final hasTelegram = (contact['telegram_chat_id']?.toString() ?? '').isNotEmpty;
    final notifyCall = contact['notify_call'] == true || contact['notify_call'] == 1;
    final notifyTelegram = contact['notify_telegram'] == true || contact['notify_telegram'] == 1;

    return AppCard(
      onTap: () => _openEditor(existing: contact),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 40,
                height: 40,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: AppColors.primarySoft,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  '${index + 1}',
                  style: const TextStyle(fontWeight: FontWeight.w800, color: AppColors.primary),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      contact['name']?.toString() ?? 'Contact',
                      style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '${contact['relation']?.toString().isNotEmpty == true ? '${contact['relation']} · ' : ''}'
                      '${contact['phone'] ?? ''}',
                      style: const TextStyle(fontSize: 12, color: AppColors.inkMuted),
                    ),
                  ],
                ),
              ),
              IconButton(
                icon: const Icon(Icons.delete_outline, color: AppColors.danger, size: 20),
                onPressed: () => _delete(contact['id'] as int),
              ),
            ],
          ),
          const SizedBox(height: 10),
          const Divider(height: 1),
          const SizedBox(height: 6),
          SwitchListTile(
            dense: true,
            contentPadding: EdgeInsets.zero,
            title: const Text('Automated voice call', style: TextStyle(fontSize: 13)),
            value: notifyCall,
            onChanged: (value) => _toggleChannel(contact, 'notify_call', value),
          ),
          SwitchListTile(
            dense: true,
            contentPadding: EdgeInsets.zero,
            title: const Text('Telegram clip + location', style: TextStyle(fontSize: 13)),
            subtitle: hasTelegram
                ? Text(
                    'Chat ${contact['telegram_chat_id']}',
                    style: const TextStyle(fontSize: 11, color: AppColors.inkMuted),
                  )
                : const Text(
                    'No chat linked — tap the card to link one',
                    style: TextStyle(fontSize: 11, color: AppColors.warning),
                  ),
            value: notifyTelegram,
            onChanged: (value) => _toggleChannel(contact, 'notify_telegram', value),
          ),
        ],
      ),
    );
  }
}

/// Add / edit sheet, including the Telegram chat picker.
class _ContactEditor extends StatefulWidget {
  final ApiService api;
  final Map<String, dynamic>? existing;

  const _ContactEditor({required this.api, this.existing});

  @override
  State<_ContactEditor> createState() => _ContactEditorState();
}

class _ContactEditorState extends State<_ContactEditor> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _name =
      TextEditingController(text: widget.existing?['name']?.toString() ?? '');
  late final TextEditingController _phone =
      TextEditingController(text: widget.existing?['phone']?.toString() ?? '');
  late final TextEditingController _relation =
      TextEditingController(text: widget.existing?['relation']?.toString() ?? '');
  late final TextEditingController _chatId =
      TextEditingController(text: widget.existing?['telegram_chat_id']?.toString() ?? '');
  late int _priority = (widget.existing?['priority'] as num?)?.toInt() ?? 1;

  bool _saving = false;
  bool _loadingChats = false;
  String? _error;
  List<Map<String, dynamic>> _chats = const [];
  bool _telegramConfigured = true;

  @override
  void dispose() {
    _name.dispose();
    _phone.dispose();
    _relation.dispose();
    _chatId.dispose();
    super.dispose();
  }

  Future<void> _loadChats() async {
    setState(() => _loadingChats = true);
    final response = await widget.api.telegramChats();
    if (!mounted) return;
    setState(() {
      _loadingChats = false;
      _telegramConfigured = response?['configured'] == true;
      _chats = List<Map<String, dynamic>>.from(response?['chats'] as Iterable? ?? const []);
    });
  }

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    final userId = AppSession.instance.userId;
    final existingId = widget.existing?['id'] as int?;

    final result = existingId == null
        ? await widget.api.addContact(
            userId: userId,
            name: _name.text.trim(),
            phone: _phone.text.trim(),
            relation: _relation.text.trim(),
            telegramChatId: _chatId.text.trim().isEmpty ? null : _chatId.text.trim(),
            priority: _priority,
          )
        : await widget.api.updateContact(
            contactId: existingId,
            userId: userId,
            fields: {
              'name': _name.text.trim(),
              'phone': _phone.text.trim(),
              'relation': _relation.text.trim(),
              'telegram_chat_id': _chatId.text.trim(),
              'priority': _priority,
            },
          );

    if (!mounted) return;
    setState(() => _saving = false);
    if (result == null) {
      setState(() => _error = 'Could not save the contact. Is the backend running?');
      return;
    }
    Navigator.pop(context, true);
  }

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.of(context).viewInsets.bottom;
    return Padding(
      padding: EdgeInsets.only(bottom: bottomInset),
      child: Container(
        decoration: const BoxDecoration(
          color: AppColors.canvas,
          borderRadius: BorderRadius.vertical(top: Radius.circular(26)),
        ),
        padding: const EdgeInsets.fromLTRB(20, 18, 20, 26),
        child: SingleChildScrollView(
          child: Form(
            key: _formKey,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Center(
                  child: Container(
                    width: 42,
                    height: 4,
                    decoration: BoxDecoration(
                      color: AppColors.line,
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                ),
                const SizedBox(height: 18),
                Text(
                  widget.existing == null ? 'Add emergency contact' : 'Edit contact',
                  style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _name,
                  decoration: const InputDecoration(labelText: 'Full name'),
                  validator: (v) => (v == null || v.trim().isEmpty) ? 'Name is required' : null,
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: _phone,
                  keyboardType: TextInputType.phone,
                  decoration: const InputDecoration(
                    labelText: 'Phone number',
                    helperText: 'Include the country code, e.g. +9198…, for the automated call',
                  ),
                  validator: (v) => (v == null || v.trim().isEmpty) ? 'Phone is required' : null,
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: _relation,
                  decoration: const InputDecoration(labelText: 'Relation (parent, friend…)'),
                ),
                const SizedBox(height: 16),
                const SectionLabel('Escalation order'),
                Row(
                  children: List.generate(4, (index) {
                    final value = index + 1;
                    final selected = _priority == value;
                    return Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: ChoiceChip(
                        label: Text('$value'),
                        selected: selected,
                        selectedColor: AppColors.primarySoft,
                        onSelected: (_) => setState(() => _priority = value),
                      ),
                    );
                  }),
                ),
                const SizedBox(height: 18),
                const SectionLabel('Telegram delivery'),
                TextFormField(
                  controller: _chatId,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(
                    labelText: 'Telegram chat id',
                    helperText: 'The clip, class, risk score, and location go here',
                  ),
                ),
                const SizedBox(height: 10),
                OutlinedButton.icon(
                  onPressed: _loadingChats ? null : _loadChats,
                  icon: _loadingChats
                      ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.search, size: 18),
                  label: const Text('FIND CHATS THAT STARTED THE BOT'),
                ),
                if (!_telegramConfigured)
                  const Padding(
                    padding: EdgeInsets.only(top: 10),
                    child: Text(
                      'The backend has no TELEGRAM_BOT_TOKEN yet, so no chats can be listed. '
                      'Alerts will be simulated until it is set.',
                      style: TextStyle(fontSize: 11, color: AppColors.warning, height: 1.5),
                    ),
                  ),
                ..._chats.map(
                  (chat) => ListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.chat_bubble_outline, size: 18),
                    title: Text(chat['name']?.toString() ?? '', style: const TextStyle(fontSize: 13)),
                    subtitle: Text(
                      'chat ${chat['chat_id']}',
                      style: const TextStyle(fontSize: 11, color: AppColors.inkMuted),
                    ),
                    trailing: const Icon(Icons.add_circle_outline, size: 18, color: AppColors.primary),
                    onTap: () => setState(() => _chatId.text = chat['chat_id']?.toString() ?? ''),
                  ),
                ),
                if (_error != null) ...[
                  const SizedBox(height: 12),
                  Text(_error!, style: const TextStyle(fontSize: 12, color: AppColors.danger)),
                ],
                const SizedBox(height: 20),
                PressableScale(
                  child: ElevatedButton(
                    onPressed: _saving ? null : _save,
                    child: Text(_saving ? 'SAVING…' : 'SAVE CONTACT'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
