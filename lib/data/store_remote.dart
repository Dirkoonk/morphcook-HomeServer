import 'dart:convert';
import 'dart:js_interop';
import 'dart:typed_data';

import 'package:web/web.dart' as web;

import '../models/profile.dart';
import 'store.dart';

/// Web persistence: the whole state is mirrored in memory (so the synchronous
/// reads of [PersistenceStore] keep working) and every write goes through to
/// the home-server API (`server/server.py`), shared by all devices.
class RemoteStore implements PersistenceStore {
  RemoteStore({this.baseUrl = 'api'});

  final String baseUrl;
  final Map<String, String> _kv = {};
  final Map<String, Uint8List> _images = {};

  static const _profileKey = 'pref.profile';
  static const _onboardingKey = 'pref.onboarding_complete';

  Future<web.Response> _request(
    String method,
    String path, {
    JSAny? body,
    String? contentType,
  }) async {
    final response = await web.window
        .fetch(
          '$baseUrl/$path'.toJS,
          web.RequestInit(
            method: method,
            body: body,
            headers: {
              if (contentType != null) 'Content-Type': contentType,
            }.jsify()!,
          ),
        )
        .toDart;
    if (!response.ok) {
      throw StateError('Server error ${response.status} on $method $path');
    }
    return response;
  }

  Future<void> _sendText(String method, String path, String text) =>
      _request(method, path, body: text.toJS, contentType: 'text/plain');

  Future<void> _sendJson(String path, Object json) => _request(
    'POST',
    path,
    body: jsonEncode(json).toJS,
    contentType: 'application/json',
  );

  @override
  Future<void> open() async {
    final response = await _request('GET', 'state');
    final text = (await response.text().toDart).toDart;
    final state = jsonDecode(text) as Map<String, dynamic>;
    _kv
      ..clear()
      ..addAll((state['kv'] as Map<String, dynamic>).cast<String, String>());
    _images.clear();
    for (final id in (state['images'] as List).cast<String>()) {
      final response = await _request('GET', 'image/$id');
      final buffer = await response.arrayBuffer().toDart;
      _images[id] = buffer.toDart.asUint8List();
    }
  }

  @override
  Profile? loadProfile() {
    final raw = _kv[_profileKey];
    if (raw == null) return null;
    try {
      return Profile.fromJson(json.decode(raw) as Map<String, dynamic>);
    } catch (_) {
      return null;
    }
  }

  @override
  Future<void> saveProfile(Profile profile) =>
      putCollection(_profileKey, json.encode(profile.toJson()));

  @override
  bool get onboardingComplete => _kv[_onboardingKey] == 'true';

  @override
  Future<void> setOnboardingComplete(bool value) =>
      putCollection(_onboardingKey, value.toString());

  @override
  String? getCollection(String key) => _kv[key];

  @override
  Future<void> putCollection(String key, String jsonText) async {
    await _sendText('PUT', 'kv/$key', jsonText);
    _kv[key] = jsonText;
  }

  @override
  Future<void> putCollections(Map<String, String> collections) async {
    await _sendJson('kv', collections);
    _kv.addAll(collections);
  }

  @override
  Map<String, Uint8List> loadRecipeImageBytes() => {
    for (final e in _images.entries) e.key: Uint8List.fromList(e.value),
  };

  @override
  Future<void> putRecipeImageBytes(String recipeId, Uint8List bytes) =>
      putRecipeImageBytesBatch({recipeId: bytes});

  @override
  Future<void> putRecipeImageBytesBatch(Map<String, Uint8List> images) async {
    await _sendJson('images', {
      for (final e in images.entries) e.key: base64Encode(e.value),
    });
    for (final e in images.entries) {
      _images[e.key] = Uint8List.fromList(e.value);
    }
  }

  @override
  Future<void> removeRecipeImageBytes(String recipeId) =>
      removeRecipeImageBytesBatch([recipeId]);

  @override
  Future<void> removeRecipeImageBytesBatch(Iterable<String> recipeIds) async {
    final ids = recipeIds.toList();
    await _sendJson('images/delete', ids);
    ids.forEach(_images.remove);
  }

  @override
  Future<void> clearRecipeImageBytes() =>
      removeRecipeImageBytesBatch(_images.keys);

  @override
  Future<void> clearAll() async {
    await _request('POST', 'clear');
    _kv.clear();
    _images.clear();
  }
}
