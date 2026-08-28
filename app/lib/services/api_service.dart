import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;

import 'session_service.dart';

/// Thin client for the Echo backend.
///
/// Every method returns null / false on failure rather than throwing, and the
/// screens surface that explicitly -- a safety app must never look like it is
/// working when the backend is unreachable.
class ApiService {
  final String baseUrl;

  ApiService({String? baseUrl}) : baseUrl = baseUrl ?? AppSession.apiBaseUrl;

  // ------------------------------------------------------------------
  // Detection
  // ------------------------------------------------------------------

  /// Sends a 2-second or 5-second audio chunk to the backend for threat detection.
  Future<Map<String, dynamic>?> detectAudio({
    required File audioFile,
    required double duration,
    bool mediaPlayback = false,
    bool suddenMotion = false,
    String? primaryCandidate,
    double? primaryConfidence,
    double sensitivityThreshold = 0.50,
    String userId = 'echo_mobile_client',
    String contextSource = 'platform_signal',
    String profile = 'real',
  }) async {
    try {
      final uri = Uri.parse('$baseUrl/detect');
      final request = http.MultipartRequest('POST', uri)
        ..fields['duration'] = duration.toString()
        ..fields['media_playback'] = mediaPlayback.toString()
        ..fields['sudden_motion'] = suddenMotion.toString()
        ..fields['sensitivity_threshold'] = sensitivityThreshold.toString()
        ..fields['user_id'] = userId
        ..fields['context_source'] = contextSource
        ..fields['profile'] = profile
        ..files.add(await http.MultipartFile.fromPath('file', audioFile.path));
      if (primaryCandidate != null && primaryConfidence != null) {
        request.fields['primary_candidate'] = primaryCandidate;
        request.fields['primary_confidence'] = primaryConfidence.toString();
      }

      final streamedResponse = await request.send();
      final response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode == 200) {
        return json.decode(response.body) as Map<String, dynamic>;
      }
      print('Detect request failed: ${response.statusCode} ${response.body}');
      return null;
    } catch (e) {
      print('Error calling detect endpoint: $e');
      return null;
    }
  }

  /// Same as [detectAudio] but for audio bytes that were not written to a
  /// local file first (used by the demo screen's prepared-clip injection).
  Future<Map<String, dynamic>?> detectAudioBytes({
    required List<int> audioBytes,
    required String filename,
    required double duration,
    bool mediaPlayback = false,
    bool suddenMotion = false,
    double sensitivityThreshold = 0.50,
    String userId = 'echo_mobile_client',
    String contextSource = 'browser_manual',
    String profile = 'real',
  }) async {
    try {
      final uri = Uri.parse('$baseUrl/detect');
      final request = http.MultipartRequest('POST', uri)
        ..fields['duration'] = duration.toString()
        ..fields['media_playback'] = mediaPlayback.toString()
        ..fields['sudden_motion'] = suddenMotion.toString()
        ..fields['sensitivity_threshold'] = sensitivityThreshold.toString()
        ..fields['user_id'] = userId
        ..fields['context_source'] = contextSource
        ..fields['profile'] = profile
        ..files.add(http.MultipartFile.fromBytes('file', audioBytes, filename: filename));

      final streamedResponse = await request.send();
      final response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode == 200) {
        return json.decode(response.body) as Map<String, dynamic>;
      }
      print('Detect request failed: ${response.statusCode} ${response.body}');
      return null;
    } catch (e) {
      print('Error calling detect endpoint: $e');
      return null;
    }
  }

  /// Which classifier heads the backend can serve (real / demo) and whether
  /// each one is actually loaded.
  Future<Map<String, dynamic>?> getProfiles() => _getJson('/profiles');

  /// Fetches a bundled demo clip served by the backend.
  Future<List<int>?> fetchDemoClip(String soundClass) async {
    for (final path in [
      '/data/processed_demo/$soundClass/${soundClass}_000.wav',
      '/data/processed/$soundClass/${soundClass}_esc50_000.wav',
      '/data/synthetic/$soundClass/${soundClass}_000.wav',
    ]) {
      try {
        final response = await http.get(Uri.parse('$baseUrl$path'));
        if (response.statusCode == 200) return response.bodyBytes;
      } catch (e) {
        print('Error fetching demo clip $path: $e');
      }
    }
    return null;
  }

  /// Fetches the shared per-class guidance copy the browser dashboard uses,
  /// so the mobile app does not maintain a second, driftable copy of it.
  Future<Map<String, dynamic>?> fetchGuidanceRules() => _getJson('/guidance_rules.json');

  // ------------------------------------------------------------------
  // Events
  // ------------------------------------------------------------------

  Future<bool> logEvent({
    required String userId,
    required String className,
    required double primaryConf,
    required double verificationConf,
    required int riskScore,
    required String riskLevel,
  }) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/events'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({
          'user_id': userId,
          'class_name': className,
          'primary_conf': primaryConf,
          'verification_conf': verificationConf,
          'risk_score': riskScore,
          'risk_level': riskLevel,
        }),
      );
      return response.statusCode == 200;
    } catch (e) {
      print('Error logging event: $e');
      return false;
    }
  }

  Future<List<Map<String, dynamic>>?> getEventHistory(String userId) =>
      _getJsonList('/events/$userId');

  Future<bool> clearEventHistory(String userId) async {
    try {
      final response = await http.delete(Uri.parse('$baseUrl/events/$userId'));
      return response.statusCode == 200;
    } catch (e) {
      print('Error clearing event history: $e');
      return false;
    }
  }

  // ------------------------------------------------------------------
  // Contacts
  // ------------------------------------------------------------------

  Future<List<Map<String, dynamic>>?> getContacts(String userId) =>
      _getJsonList('/contacts/$userId');

  Future<Map<String, dynamic>?> addContact({
    required String userId,
    required String name,
    required String phone,
    required String relation,
    String? telegramChatId,
    int priority = 100,
    bool notifyCall = true,
    bool notifyTelegram = true,
  }) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/contacts'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({
          'user_id': userId,
          'name': name,
          'phone': phone,
          'relation': relation,
          'telegram_chat_id': telegramChatId,
          'priority': priority,
          'notify_call': notifyCall,
          'notify_telegram': notifyTelegram,
        }),
      );
      if (response.statusCode == 200) {
        return json.decode(response.body) as Map<String, dynamic>;
      }
      return null;
    } catch (e) {
      print('Error adding contact: $e');
      return null;
    }
  }

  Future<Map<String, dynamic>?> updateContact({
    required int contactId,
    required String userId,
    Map<String, dynamic> fields = const {},
  }) async {
    try {
      final response = await http.patch(
        Uri.parse('$baseUrl/contacts/$contactId?user_id=$userId'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode(fields),
      );
      if (response.statusCode == 200) {
        return json.decode(response.body) as Map<String, dynamic>;
      }
      print('Contact update failed: ${response.statusCode} ${response.body}');
      return null;
    } catch (e) {
      print('Error updating contact: $e');
      return null;
    }
  }

  /// The backend scopes deletion by user id; omitting it always 404'd.
  Future<bool> deleteContact(int contactId, {required String userId}) async {
    try {
      final response = await http.delete(
        Uri.parse('$baseUrl/contacts/$contactId?user_id=$userId'),
      );
      return response.statusCode == 200;
    } catch (e) {
      print('Error deleting contact: $e');
      return false;
    }
  }

  // ------------------------------------------------------------------
  // Emergency escalation
  // ------------------------------------------------------------------

  /// Creates an incident and arms the countdown before contacts are called
  /// and messaged. Returns the incident (including `escalation_armed` and
  /// `gate_reason`) or null if the backend could not be reached.
  Future<Map<String, dynamic>?> createIncident({
    required String userId,
    required String className,
    String? rawClass,
    String profile = 'real',
    double primaryConf = 0.0,
    double verificationConf = 0.0,
    int riskScore = 0,
    String riskLevel = 'NORMAL',
    bool verified = true,
    double? latitude,
    double? longitude,
    double? accuracyM,
    String? placeLabel,
    String? userLabel,
    bool force = false,
    List<int>? clipBytes,
    String clipFilename = 'incident.wav',
  }) async {
    try {
      final request = http.MultipartRequest('POST', Uri.parse('$baseUrl/incidents'))
        ..fields['user_id'] = userId
        ..fields['class_name'] = className
        ..fields['profile'] = profile
        ..fields['primary_conf'] = primaryConf.toString()
        ..fields['verification_conf'] = verificationConf.toString()
        ..fields['risk_score'] = riskScore.toString()
        ..fields['risk_level'] = riskLevel
        ..fields['verified'] = verified.toString()
        ..fields['force'] = force.toString();
      if (rawClass != null) request.fields['raw_class'] = rawClass;
      if (latitude != null) request.fields['latitude'] = latitude.toString();
      if (longitude != null) request.fields['longitude'] = longitude.toString();
      if (accuracyM != null) request.fields['accuracy_m'] = accuracyM.toString();
      if (placeLabel != null) request.fields['place_label'] = placeLabel;
      if (userLabel != null) request.fields['user_label'] = userLabel;
      if (clipBytes != null && clipBytes.isNotEmpty) {
        request.files.add(http.MultipartFile.fromBytes('clip', clipBytes, filename: clipFilename));
      }

      final response = await http.Response.fromStream(await request.send());
      if (response.statusCode == 200) {
        return json.decode(response.body) as Map<String, dynamic>;
      }
      print('Incident creation failed: ${response.statusCode} ${response.body}');
      return null;
    } catch (e) {
      print('Error creating incident: $e');
      return null;
    }
  }

  Future<Map<String, dynamic>?> getIncident(String incidentId) =>
      _getJson('/incidents/$incidentId');

  Future<List<Map<String, dynamic>>?> getIncidentHistory(String userId) =>
      _getJsonList('/incidents/user/$userId');

  Future<Map<String, dynamic>?> cancelIncident({
    required String incidentId,
    required String userId,
    String note = 'Marked safe by the user.',
  }) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/incidents/$incidentId/cancel'),
        body: {'user_id': userId, 'note': note},
      );
      if (response.statusCode == 200) {
        return json.decode(response.body) as Map<String, dynamic>;
      }
      return null;
    } catch (e) {
      print('Error cancelling incident: $e');
      return null;
    }
  }

  Future<Map<String, dynamic>?> dispatchIncidentNow({
    required String incidentId,
    String? userLabel,
  }) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/incidents/$incidentId/dispatch'),
        body: {if (userLabel != null) 'user_label': userLabel},
      );
      if (response.statusCode == 200) {
        return json.decode(response.body) as Map<String, dynamic>;
      }
      print('Dispatch failed: ${response.statusCode} ${response.body}');
      return null;
    } catch (e) {
      print('Error dispatching incident: $e');
      return null;
    }
  }

  Future<Map<String, dynamic>?> escalationStatus() => _getJson('/escalation/status');

  Future<Map<String, dynamic>?> escalationReadiness(String userId) =>
      _getJson('/escalation/readiness/$userId');

  Future<Map<String, dynamic>?> sendEscalationTest({
    required String userId,
    String? userLabel,
  }) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/escalation/test'),
        body: {'user_id': userId, if (userLabel != null) 'user_label': userLabel},
      );
      if (response.statusCode == 200) {
        return json.decode(response.body) as Map<String, dynamic>;
      }
      print('Escalation test failed: ${response.statusCode} ${response.body}');
      return null;
    } catch (e) {
      print('Error sending escalation test: $e');
      return null;
    }
  }

  Future<Map<String, dynamic>?> telegramChats() => _getJson('/telegram/chats');

  // ------------------------------------------------------------------
  // Places
  // ------------------------------------------------------------------

  Future<List<Map<String, dynamic>>?> getNearbyPlaces({
    required double lat,
    required double lng,
    required String type,
  }) async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/nearby?lat=$lat&lng=$lng&type=$type'));
      if (response.statusCode == 200) {
        final data = json.decode(response.body) as Map<String, dynamic>;
        if (data['status'] == 'success' || data['status'] == 'fallback') {
          return List<Map<String, dynamic>>.from(data['results']);
        }
      }
      return null;
    } catch (e) {
      print('Error fetching nearby places: $e');
      return null;
    }
  }

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------

  Future<Map<String, dynamic>?> _getJson(String path) async {
    try {
      final response = await http.get(Uri.parse('$baseUrl$path'));
      if (response.statusCode == 200) {
        return json.decode(response.body) as Map<String, dynamic>;
      }
      return null;
    } catch (e) {
      print('GET $path failed: $e');
      return null;
    }
  }

  Future<List<Map<String, dynamic>>?> _getJsonList(String path) async {
    try {
      final response = await http.get(Uri.parse('$baseUrl$path'));
      if (response.statusCode == 200) {
        return List<Map<String, dynamic>>.from(json.decode(response.body));
      }
      return null;
    } catch (e) {
      print('GET $path failed: $e');
      return null;
    }
  }
}
