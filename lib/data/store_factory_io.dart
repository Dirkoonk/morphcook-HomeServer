import 'store.dart';

/// Mobile/desktop: local Hive storage.
PersistenceStore createStore() => HiveStore();
