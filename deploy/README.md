# Home-server deployment

1. On a machine with Flutter 3.41.9:
   ```sh
   flutter pub get
   flutter build web --release
   ```
2. `build/` is git-ignored: `git pull` the repo on the server and copy the build over, e.g. `scp -r build/web <user>@<server>:morphcook-HomeServer/build/`, then on the server:
   ```sh
   docker compose up -d --build
   ```
3. Open `http://<server-ip>:8085` from any device in the home network.

All data (profile, personal recipes, plans, photos) lives in the `morphcook-data`
Docker volume (SQLite). Back it up with `docker run --rm -v morphcook_morphcook-data:/d -v $PWD:/b alpine tar czf /b/morphcook-data.tgz -C /d .`.
There is no authentication: expose the port only inside the home network.
