import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Signed-in user and app-wide settings.
///
/// The sign-in here is deliberately local: any credentials are accepted and
/// nothing is transmitted or verified. It exists to give the app a real
/// account shell (a stable user id that scopes contacts, events, and
/// incidents on the backend, plus a display name used in the alert message
/// contacts receive) without pretending to be authentication. Every screen
/// that shows the session says so, and [isVerifiedAccount] is false so no
/// other code can mistake it for a real login.
class SessionUser {
  final String userId;
  final String email;
  final String displayName;
  final String phone;

  const SessionUser({
    required this.userId,
    required this.email,
    required this.displayName,
    this.phone = '',
  });

  bool get isVerifiedAccount => false;

  Map<String, String> toMap() => {
        'userId': userId,
        'email': email,
        'displayName': displayName,
        'phone': phone,
      };

  static SessionUser fromMap(Map<String, dynamic> map) => SessionUser(
        userId: map['userId']?.toString() ?? 'echo_user',
        email: map['email']?.toString() ?? '',
        displayName: map['displayName']?.toString() ?? 'Echo user',
        phone: map['phone']?.toString() ?? '',
      );
}

class AppSession {
  AppSession._();
  static final AppSession instance = AppSession._();

  /// Backend base URL. Android emulator default; override at build time:
  /// `flutter run --dart-define=ECHO_API_URL=http://192.168.1.5:8010`
  static const String apiBaseUrl = String.fromEnvironment(
    'ECHO_API_URL',
    defaultValue: 'http://10.0.2.2:8010',
  );

  final ValueNotifier<SessionUser?> user = ValueNotifier<SessionUser?>(null);
  final ValueNotifier<bool> restoring = ValueNotifier<bool>(true);

  /// Selected classifier head: 'real' or 'demo'. Lives here because the live
  /// monitor, the demo screen, and settings all need the same answer.
  final ValueNotifier<String> modelProfile = ValueNotifier<String>('real');

  /// Whether a verified high-risk detection may call and message contacts.
  final ValueNotifier<bool> autoEscalation = ValueNotifier<bool>(true);

  SessionUser? get currentUser => user.value;
  String get userId => user.value?.userId ?? 'echo_guest';
  String get displayName => user.value?.displayName ?? 'An Echo user';

  static const _kUser = 'echo_session_user';
  static const _kProfile = 'echo_model_profile';
  static const _kAutoEscalation = 'echo_auto_escalation';

  Future<void> restore() async {
    restoring.value = true;
    try {
      final prefs = await SharedPreferences.getInstance();
      final stored = prefs.getStringList(_kUser);
      if (stored != null && stored.length >= 3) {
        user.value = SessionUser(
          userId: stored[0],
          email: stored[1],
          displayName: stored[2],
          phone: stored.length > 3 ? stored[3] : '',
        );
      }
      modelProfile.value = prefs.getString(_kProfile) ?? 'real';
      autoEscalation.value = prefs.getBool(_kAutoEscalation) ?? true;
    } finally {
      restoring.value = false;
    }
  }

  /// Local sign-in. Accepts whatever is typed; derives a stable user id from
  /// the identifier so the same person returns to the same contacts and
  /// history on the backend.
  Future<SessionUser> signIn({
    required String identifier,
    String? displayName,
    String phone = '',
  }) async {
    final cleaned = identifier.trim().toLowerCase();
    final slug = cleaned
        .replaceAll(RegExp(r'[^a-z0-9]+'), '_')
        .replaceAll(RegExp(r'^_+|_+$'), '');
    final userId = slug.isEmpty ? 'echo_user' : 'echo_$slug';
    final name = (displayName == null || displayName.trim().isEmpty)
        ? _nameFromIdentifier(cleaned)
        : displayName.trim();

    final session = SessionUser(
      userId: userId,
      email: identifier.trim(),
      displayName: name,
      phone: phone.trim(),
    );

    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(
      _kUser,
      [session.userId, session.email, session.displayName, session.phone],
    );
    user.value = session;
    return session;
  }

  Future<void> signOut() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kUser);
    user.value = null;
  }

  Future<void> setModelProfile(String profile) async {
    modelProfile.value = profile;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kProfile, profile);
  }

  Future<void> setAutoEscalation(bool enabled) async {
    autoEscalation.value = enabled;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_kAutoEscalation, enabled);
  }

  static String _nameFromIdentifier(String identifier) {
    final local = identifier.split('@').first;
    if (local.isEmpty) return 'Echo user';
    final words = local.split(RegExp(r'[._\-\s]+')).where((w) => w.isNotEmpty);
    return words
        .map((w) => w[0].toUpperCase() + (w.length > 1 ? w.substring(1) : ''))
        .join(' ');
  }
}
