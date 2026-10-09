import 'store.dart';
import 'store_remote.dart';

/// Web: shared storage on the home server.
PersistenceStore createStore() => RemoteStore();
