# Drivecheck — veřejný odhad ceny

Statická aplikace na GitHub Pages. Čísla počítá stejný engine jako interní Drivecheck; inzeráty jsou v šifrovaném snapshotu, fotky se nenačítají.

## Heslo

Stejné firemní heslo jako při šifrování snapshotu. V Actions je v secretu `SNAPSHOT_PASSWORD`. Do gitu nepatří.

## Crawler

Workflow `pages-snapshot` každé 4. hodinu (`0 */6 * * *`) obnoví snapshot, spustí jeden slušný `seed --source all`, znovu zašifruje dump a nasadí Pages.

Ruční nasazení bez crawlu (jen aktuální Release): **Actions → pages-snapshot → Run workflow** (crawl vypnutý).

Ruční crawl: totéž a zaškrtněte **crawl**.

## Bootstrap

1. Secret `SNAPSHOT_PASSWORD`
2. Release tag `snapshot` se soubory `snapshot.bin` + `snapshot.meta.json`
3. Pages source = GitHub Actions
