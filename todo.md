# Bootloader: dwie wersje

Dwie wersje bootloadera i nic pomiędzy.
`plain` jest bez zabezpieczeń, jak dziś.
`key` daje wysoki poziom zabezpieczeń bez dziur, ale nie tak wysoki, żeby przeszkadzał w codziennej pracy.

Stan dziś: obraz ma nagłówek `{magic, size}` pod `0x200` i CRC32 pod `[size]`, które urządzenie dopisuje przy stage'owaniu.
Bootloader sprawdza to CRC przy każdym starcie, a skasowane CRC z programatora przepuszcza.

## Stan

### Wydanie 0.4.5, ścieżka `plain`

Zrobione w Forge, 214 testów, sprawdzone na buildach G0C1 i WB55, jeszcze nie na sprzęcie:

- `utils/hexfile.py`: mapa adres → bajt, zgodna z `objcopy` na prawdziwych obrazach
- `--pack`: build daje `-flash.hex`, a pod bootloaderem CRC w trailerze, bootloader z przodu i `-update.bin` obok
- `make flash` i F5 idą jednym plikiem `-flash.hex`, makefile i `launch.json` nie wiedzą nic o bootloaderze
- `dist` daje `<nazwa>.hex` z pełnym obrazem, a pod bootloaderem także `<nazwa>.bin` z samym obrazem do aktualizacji
- `--program <plik>` wgrywa `.hex` z dista tym samym poleceniem co `make flash`, surowego `.bin` odmawia
- `make stack` bierze CubeProgrammera z domyślnego miejsca albo mówi, skąd go pobrać

Przed wydaniem test na Nucleo:

1. Projekt bez bootloadera: `make flash`, aplikacja startuje.
2. Projekt z `-B` po `make erase`: `make flash`, bootloader odpala aplikację.
3. F5: staje w `main`, breakpoint i krok działają.
4. `make dist TAG=…`, potem `--program` z tym plikiem.
5. Na Nucleo-WB55 jeszcze raz punkt 2, bo bootloader ma tam 16kB i inny układ slotów.

Aktualizacja w polu plikiem `.hex` z dista 0.4.5 wymaga xaeian 1.0.0: `Shell.boot` wycina obraz spod adresu slotu.
Starszy xaeian czyta nagłówek od początku pliku, a pełny obraz zaczyna się od bootloadera, więc wysłałby bootloader.
Plik `.bin` z dista działa z każdym.

### Gotowe, ale jeszcze nieużywane

`utils/ed25519.py` zgadza się z wektorami RFC 8032 i z OpenSSL.
Czeka na tryb `key`, dziś nic go nie importuje.

### Do zrobienia

Cały tryb `key` i wszystko po stronie Core, w etapach: [pkt 11](#11-co-zostało).
Opis poziomów bezpieczeństwa dla ludzi i pod regulacje: [security.md](.r2/security.md).

---

## 1. W skrócie

| | `plain` | `key` |
| --- | --- | --- |
| Wybór w `main.h` | brak `PRO_BOOT_KEY` | `PRO_BOOT_KEY` |
| Rozmiar bootloadera | jak dziś: G0 8kB, WB 16kB | większy, do zmierzenia |
| Przy starcie sprawdza | nagłówek, CRC | nagłówek, CRC, podpis |
| Przy instalacji sprawdza | to samo | to samo i epokę |
| Blokada SWD | nie | `--lock`: RDP1, WRP, wyłączony `BOOT0` |
| Dla kogo | dev, hobby, domyślnie | produkcja |

Obie wersje mają jeden format obrazu, ten sam mailbox, ten sam protokół `UPDATE` i ten sam `make`, F5, `dist`.
Różni je tylko to, co bootloader sprawdza.
Tryb należy do projektu, nie do workspace, bo jeden workspace trzyma wiele produktów.

## 2. `plain`

**Zero zabezpieczeń, tylko bezpieczniki przed wypadkiem.**

Chroni przed:

- uszkodzonym transferem, przez CRC jak dziś,
- przerwą zasilania przy instalacji, jak dziś,
- obrazem na inny chip (`chip`) i pod inny slot (`origin`).
  To nowość za kilkadziesiąt bajtów, bo taki obraz to cegła, a nie atak.

Nie chroni przed niczym, co robi człowiek.
Każdy obraz z poprawnym CRC wchodzi przez `UPDATE`, programator wgrywa wszystko.
To dzisiejsze zachowanie i tak ma zostać.

## 3. `key`

**Bootloader skacze tylko do obrazu podpisanego kluczem produktu, przy każdym starcie.**
Nie „przy instalacji”, nie „raz i zapamiętaj”.
Nie ma stanu „zweryfikowany” do przechowywania, więc nic nie może się rozjechać.
Obraz z programatora podlega temu samemu co obraz z `UPDATE`.

> **Nota:** Bootloader `key` bez wpisanego klucza (32B `0xFF`) nie startuje niczego, czeka na SWD.
> Nie ma trybu „keyed, ale przepuszcza”, bo to byłaby druga droga do `plain`, tylko przez pomyłkę.

### Epoka

`#define PRO_BOOT_EPOCH 0` w `main.h`, pod `PRO_BOOT_KEY`.
Liczba siedzi w nagłówku, pod podpisem.
Przy instalacji bootloader odmawia obrazu z epoką niższą niż obraz w slocie.

- Zwykłe release'y jej nie ruszają, więc cofanie wersji i gałęzie LTS działają normalnie.
- Podbijasz ją tylko wtedy, gdy release zamyka dziurę bezpieczeństwa.
  Urządzenie, które go przyjęło, nie wróci już do dziurawej wersji.
- Podbijaj ją tylko w przetestowanym release, bo po nim nie ma odwrotu.
  Zły release z nową epoką naprawiasz wyłącznie do przodu.
- Decyduje bootloader, nie aplikacja, bo przy downgradzie to właśnie aplikację atakujący podmienia.
- Odniesieniem jest nagłówek obrazu w slocie, bez licznika w OTP.
  Zgubić je można tylko zapisem flasha, czyli programatorem, który zamyka RDP1, albo exploitem.
- Programator epoki nie sprawdza, bo to fizyczny dostęp, a ten zamyka RDP1.
- Dopóki epoka wynosi `0`, mechanizm jest niewidoczny.

### Klucze

- **Klucz produktu**: `PRO_BOOT_KEY` to jego publiczna część, prywatna leży zaszyfrowana hasłem.
  Używa go wyłącznie `make dist`.
- **Klucz deweloperski**: per maszyna, bez hasła, Forge tworzy go sam.
  Build, `make flash` i F5 podpisują zawsze nim, także na maszynie release.

Nikt nie potrzebuje klucza produktu do codziennej pracy, a obraz produkcyjny powstaje tylko w `dist`.
Szczegóły w [pkt 6](#6-klucze).

### Blokada

`opencplc --lock` ustawia profil produkcyjny option bytes, tylko na wyraźne żądanie, z pytaniem `[YES/NO]`:

1. Czyta przez SWD klucz z bootloadera na płytce i odmawia, gdy to nie `PRO_BOOT_KEY`.
2. Ustawia WRP na stronach bootloadera, bez strony mailboxa, do której pisze aplikacja.
3. Wyłącza start z bootloadera w ROM (pin `BOOT0`).
4. Na końcu ustawia RDP1.

Wszystko idzie przez openocd, tym samym narzędziem co `make flash`.
Nasz `openocd-0.12` ma w sterowniku `stm32l4x`, używanym przez G0 i WB, polecenia `lock`, `option_write` i `option_load`.

Fabryka robi `opencplc --program <plik z dist> --lock`.
`boot info` pokazuje `rdp`, a konsola ostrzega, gdy urządzenie z kluczem produktu nie jest zablokowane.

> **Uwaga:** Bez RDP1 podpis zamyka tylko łącze aktualizacji, a ktoś z programatorem obejdzie go bez trudu.
> W dokumentacji wprost: zamknięte urządzenie to `key` + `--lock`, każde z osobna zostawia otwarte drzwi.

### Granice

`key` chroni przed:

- obcym obrazem przez `UPDATE`,
- downgradem poniżej epoki,
- odczytem i zapisem przez SWD i bootloader w ROM, po `--lock`,
- obrazem deweloperskim na urządzeniu produkcyjnym.

`key` świadomie nie chroni przed:

- exploitem w działającej aplikacji, który przestawi option bytes i nadpisze bootloader.
  To jedyna furtka i wymaga najpierw dziury w aplikacji,
- podejrzeniem treści firmware: obraz leci jawnie, chyba że aplikacja szyfruje łącze albo plik,
- glitchingiem i side-channel.

### Czego celowo nie ma

Żeby `key` nie przeszkadzał:

- pełnego wersjonowania, w którym każdy release działa w jedną stronę,
- securable area na G0, której WB i tak nie ma,
- sprzętowego watchdoga w `--lock`, od zawieszenia jest przycisk reset,
- RDP2, które na zawsze zabija debugger,
- aktualizacji bootloadera w polu, bo to ryzyko cegły,
- szyfrowania w bootloaderze: poufność to zadanie aplikacji, która rozszyfrowuje przed zapisem do slotu, a bootloader sprawdza podpis jawnej treści,
- automatycznej blokady przy pierwszym starcie, bo każdy test pliku z `dist` na płytce deweloperskiej kończyłby się kasowaniem.

## 4. Scenariusze

### Twoja praca

| Czynność | `plain` | `key` |
| --- | --- | --- |
| Raz na produkt | nic | `opencplc --keygen ediphor`, hasło, kopia klucza i hasła |
| Programowanie | `make`, `make flash` | to samo |
| Debugowanie | F5 | to samo, start dłuższy o weryfikację |
| Dist | `make dist TAG=1.2.0` | to samo i hasło |
| Nagrywanie z Cube | jeden `.hex` z dista, Download | to samo, potem `opencplc --lock` |
| Podpisywanie | nie istnieje | nigdy ręcznie: build kluczem deweloperskim, dist kluczem produktu |
| Załatana dziura bezpieczeństwa | nic | `PRO_BOOT_EPOCH` o jeden w górę, potem dist |
| Aktualizacja w polu | konsola wysyła `.bin` | to samo, przy odmowie konsola pokazuje powód |

Dist daje dwa pliki: `.hex` z bootloaderem i aplikacją dla Cube i fabryki, `.bin` z samą aplikacją dla aktualizacji.
Dziś w Cube wgrywa się dwa pliki `.bin` i ręcznie wpisuje adresy, po zmianie jeden `.hex` niesie adresy sam.

W `key` w Cube:

- płytki z RDP1 nie da się nagrać, a odblokowanie kasuje cały flash,
- sam `.bin` z dista na płytce deweloperskiej nie wystartuje, bo jej bootloader ma klucz deweloperski.
  Wgrywaj zawsze `.hex`, który niesie bootloader z pasującym kluczem.

### Codzienna praca

| Sytuacja | `plain` | `key` |
| --- | --- | --- |
| F5 na świeżej płytce | bootloader i aplikacja w jednym hexie, startuje | to samo, z kluczem deweloperskim |
| F5 na płytce z bootloaderem innej wersji Core | hex nadpisuje bootloader zgodnym | to samo |
| F5 na płytce z cudzym kluczem deweloperskim | nie dotyczy | hex wgrywa bootloader z Twoim kluczem |
| Deweloper bez klucza produktu | nie dotyczy | build, flash, F5 działają, `dist` odmawia |
| Debug bootloadera | `opencplc -r boot/stm32g0`, F5 | to samo |
| Czas od resetu do `main` | jak dziś | dłużej o weryfikację, patrz [pkt 7](#czas) |

### Wydanie i produkcja

| Sytuacja | `plain` | `key` |
| --- | --- | --- |
| `make dist` | kopiuje `-flash.hex` i `-update.bin` | pyta o hasło, podpisuje kluczem produktu, kopiuje |
| `make dist` bez klucza produktu | nie dotyczy | odmawia, głośno |
| Test pliku z `dist` przed wysyłką | `opencplc --program` | `opencplc --program` na płytce bez blokady |
| Fabryka | `--program` | `--program --lock` |
| `--lock` na płytce z kluczem deweloperskim | nie dotyczy | odmawia |

### Aktualizacja w polu

| Sytuacja | `plain` | `key` |
| --- | --- | --- |
| Poprawny obraz | instaluje | instaluje |
| Przekłamanie w transferze | `BOOT_End` odrzuca po CRC, działa stara wersja | to samo |
| Przerwa zasilania w transferze | brak rekordu w mailboxie, działa stara wersja | to samo |
| Przerwa zasilania w instalacji | po restarcie instalacja od nowa | to samo |
| Obraz na inny chip | aplikacja odrzuca przed resetem (`chip`) | to samo |
| Obraz pod inny slot | aplikacja odrzuca przed resetem (`origin`) | to samo |
| Obraz bez podpisu albo z obcym kluczem | instaluje | bootloader odrzuca (`signature`), działa stara wersja |
| Obraz z kluczem deweloperskim | instaluje | bootloader odrzuca (`signature`) |
| Starsza wersja, ta sama epoka | instaluje | instaluje |
| Starsza wersja, niższa epoka | instaluje | bootloader odrzuca (`epoch`) |

Po odrzuceniu w bootloaderze aplikacja czyta wynik i mówi hostowi, dlaczego dalej działa stara wersja.

### Awarie

| Sytuacja | `plain` | `key` |
| --- | --- | --- |
| Uszkodzony slot, np. przekłamany bit | CRC nie pasuje, bootloader czeka na SWD | podpis nie pasuje, czeka na SWD, przy RDP1 serwis |
| Zawieszenie przed startem watchdoga aplikacji | przycisk reset | to samo |
| Surowy bootloader z Core, bez klucza | nie dotyczy | nic nie startuje, czeka na SWD |
| Utrata klucza produktu albo hasła | nie dotyczy | koniec aktualizacji floty, stąd kopie offline |

### Ataki

W `plain` wszystkie te drogi są otwarte, zgodnie z założeniem.
W `key` po `--lock`:

| Atak | Wynik |
| --- | --- |
| Obcy obraz przez BLE, RS, USB | odrzucony, podpis |
| Stary, dziurawy obraz | odrzucony, jeśli dziurę zamknął release z wyższą epoką |
| Odczyt firmware przez SWD | niemożliwy |
| Wgranie bootloadera `plain` przez SWD | niemożliwe, zejście z RDP1 kasuje flash |
| Pin `BOOT0` i bootloader w ROM | wyłączony |
| Podsłuchany plik aktualizacji | daje treść firmware, nic więcej |
| Skradziony plik klucza | bez hasła bezużyteczny |
| Exploit w działającej aplikacji | może nadpisać bootloader, świadoma granica |

### Serwis i przejścia

| Sytuacja | `plain` | `key` |
| --- | --- | --- |
| Urządzenie z pola do analizy | SWD czyta wszystko | zejście do RDP0 kasuje flash, zostają logi |
| Błąd w bootloaderze w polu | naprawa tylko programatorem | tylko programatorem, po skasowaniu |
| Przejście `plain` na `key` | tylko programatorem, nie przez `UPDATE` | nie dotyczy |
| Stary bootloader w polu, nowa aplikacja | instaluje, bo format to kontrakt | nie dotyczy, urządzenia `key` są nowe |
| Nowy bootloader, obraz ze starego Core | odrzuca czysto (`origin`) | to samo |
| Stary firmware, nowe narzędzie hosta | protokół bez zmian, działa | nie dotyczy |

Produkt, który ma być `key`, musi wyjść z fabryki jako `key`.

## 5. Format i kontrakt z polem

**Formaty to kontrakt z urządzeniami, które już są w polu.**
Nowa aplikacja musi się dać zainstalować przez stary bootloader `plain`, inaczej wysłane urządzenia tracą aktualizacje.
Stąd trzy zasady:

- nagłówek rośnie tylko na końcu, `magic` zostaje,
- CRC zostaje pod `[size]`, liczone jak dziś,
- rekord mailboxa `{magic, size, page, crc}` zostaje bez zmian.

### Nagłówek

Dziś `{magic, size}`, docelowo `{magic, size, origin, chip, epoch}` pod `0x200`.

- `origin`: adres, pod który obraz jest zlinkowany, z linkera.
  Bootloader odrzuca obraz pod inny slot, zamiast w niego skoczyć.
- `chip`: identyfikator z `DBGMCU->IDCODE`, obraz G0 nie wyląduje na WB.
  Bootloader porównuje go z rejestrem w działaniu, bo jeden bootloader obsługuje całą rodzinę.
- `epoch`: z `PRO_BOOT_EPOCH`, domyślnie `0`, sprawdzana tylko w `key`.

Stary bootloader czyta tylko `{magic, size}`, więc nowe pola go nie obchodzą.
Nowy bootloader w starym obrazie trafi pod `origin` na kod, który nie zgodzi się z adresem slotu, więc odrzuci go czysto.

### Trailer

`[size]` CRC32, `[size + 8]` podpis Ed25519 64B, linker rezerwuje 72B.
Flash programuje się podwójnymi słowami, stąd wyrównanie do 8.

- Plik `hex` i `bin`: trailer wypełnia Forge, CRC zawsze, podpis w `key`.
- `UPDATE`: host wysyła obraz `[0, size)` jak dziś, a CRC i podpis w `begin`.
  Urządzenie w `BOOT_End` wpisuje trailer tak, jak dziś wpisuje CRC.
- Host wysyła podpis tylko dla obrazu `key`, a urządzenie `key` jest nowe z definicji.
  Stare urządzenia widzą protokół bez zmian.
- Host przed wysłaniem porównuje `origin` obrazu z adresem slotu z `boot info`.
  To chroni też stare urządzenia, które `origin` nie sprawdzają.

Znika hack „skasowane CRC = OK”, bo każdy obraz z Forge ma CRC.
Bajty we flashu są te same bez względu na drogę.

### Kto co sprawdza

- Aplikacja w `BOOT_End`: CRC, `chip`, `origin`, czyli to, co tanie, jeszcze przed resetem.
- Bootloader przy instalacji: to samo, w `key` także podpis i `epoch`.
- Bootloader przy każdym starcie: nagłówek, `chip`, `origin`, CRC, w `key` także podpis.

Aplikacja nie nosi krypto w żadnym trybie.

### Wynik instalacji

Bootloader zostawia wynik w słowie RAM poza `.bss` i zapisuje je przy każdym starcie, żeby nie zostawała stara wartość.
`stm32wb.ld` już zostawia 8 bajtów na początku RAM, `stm32g0.ld` dostaje to samo.
Zero zapisów flash, mailbox bez zmian.

Kody: brak, zainstalowany, odrzucony z powodem `crc`, `chip`, `origin`, `signature` albo `epoch`.

### Układ pamięci

`PRO_FLASH_kB`, `boot_kB` i `boot_key_kB` wyznaczają sloty, a sloty są częścią kontraktu.
Po wysłaniu produktu nie zmieniają się: ani w projekcie, ani między wersjami Core.
Zmiana odcina aktualizacje wysłanym urządzeniom, a `origin` sprawia, że odmowa jest czysta zamiast cegły.

## 6. Klucze

Para Ed25519: 32B seed prywatny, 32B klucz publiczny.

```c
#define PRO_BOOT true
#define PRO_BOOT_KEY "8a1fe3c0...e91d"
#define PRO_BOOT_EPOCH 0
```

Zawsze w tej kolejności, `PRO_BOOT_KEY` to 64 znaki hex klucza publicznego.

- Klucz publiczny nie jest tajny, siedzi w repo razem z projektem.
- `PRO_BOOT_KEY` wymaga `PRO_BOOT true`, inaczej Forge mówi, czego brakuje.
- Forge wpisuje klucz do bootloadera `key` przy składaniu obrazu flasha, pod stałym offsetem za nagłówkiem bootloadera.
  Core dostarcza jeden bootloader `key` bez klucza, nikt nie buduje bootloadera sam.
- Prywatne klucze leżą w katalogu kluczy, Forge bierze ten, którego publiczny zgadza się z `PRO_BOOT_KEY`.
  Nazwa pliku jest dla ludzi, dopasowanie idzie po kluczu.
- `opencplc --keygen <name>` tworzy parę z hasłem i sam wpisuje `PRO_BOOT_KEY` i `PRO_BOOT_EPOCH 0` do `main.h` aktywnego projektu, zaraz pod `PRO_BOOT`, w kolejności jak wyżej.
  Przy `PRO_BOOT false` ustawia też `PRO_BOOT true`, bo `key` bez bootloadera nie ma sensu.
- Klucz o tej nazwie już istnieje: `--keygen` podpina go zamiast tworzyć nowy, np. dla drugiego projektu tego samego produktu.
  Obok prywatnego leży `<name>.pub`, więc podpięcie nie pyta o hasło.
- Projekt ma już `PRO_BOOT_KEY`: `--keygen` odmawia, bo podmiana klucza odcina urządzenia w polu.
- Istniejący plik klucza nigdy nie jest nadpisywany.
- `boot info` raportuje `key: 8a1fe3c0`, `key: none` albo `key: missing`.

### Klucz deweloperski

- Per maszyna, bez hasła, tworzony sam przy pierwszym buildzie `key`.
- Nigdy wspólny i nigdy w repo.
  MCUboot trzyma klucze testowe w repozytorium i jego dokumentacja musi ostrzegać przed wysłaniem z nimi produktu.
- Bootloader w `-flash.hex` z builda dostaje klucz deweloperski, więc płytka deweloperska zawsze startuje.

### Przechowywanie

- Windows `%LOCALAPPDATA%/OpenCPLC/keys`, Linux `~/.local/share/OpenCPLC/keys`.
  `OPENCPLC_KEYS` przenosi katalog, jak `OPENCPLC_TOOLS` narzędzia.
- Własny prosty format: klucz produktu zaszyfrowany hasłem przez `scrypt`, deweloperski bez hasła.
  PEM zgodnego z `openssl` nie ma, bo stdlib nie ma AES, a plik czyta tylko Forge.
- W CI hasło przychodzi ze zmiennej środowiskowej ustawionej jako sekret.
- Klucz produktu i hasło: dwie kopie offline, np. w menedżerze haseł.
  Utrata któregokolwiek to koniec aktualizacji dla całej floty, bo bootloadera w polu nie zmienisz.
- Wyciek klucza nie ma odwołania, klucz per produkt ogranicza szkody do jednego produktu.

## 7. Bootloader od środka

### Krypto

Ed25519 z RFC 8032, bo weryfikacja nie potrzebuje RNG, podpis jest deterministyczny i nie ma pułapek z nonce.
Klucz 32B, podpis 64B, jeden plik implementacji, ta sama ścieżka na M0+ i M4.

Kandydaci: Monocypher (~10-14kB thumb) albo c25519 (~6kB, wolniejszy).
Obaj bez zobowiązań licencyjnych: Monocypher do wzięcia na CC0, c25519 w domenie publicznej.
Z Monocypher tylko moduł opcjonalny `monocypher-ed25519`, bo domyślne EdDSA liczy BLAKE2b i nie zgodzi się z podpisem z Forge.

Symetryczny HMAC odpada: klucz w bootloaderze czytany przez SWD zdradza go na każdym egzemplarzu.

### Czas

Weryfikacja to SHA-512 nad całym obrazem i mnożenia na krzywej, a M0+ nie ma nic, co by je przyspieszało.
Rząd wielkości: pół sekundy do sekundy na G0 dla obrazu 250kB przy 64MHz, na M4 w WB kilka razy mniej.
Przy 16MHz cztery razy dłużej, więc 64MHz jest obowiązkowe.

- Przed `BOOT_Jump` bootloader przywraca zegar, latencję flasha i zasilanie do stanu po resecie.
  Aplikacja konfiguruje zegar od stanu po resecie i PLL zostawiony w biegu by ją wywrócił.
- Hash liczony w kawałkach z `IWDG_Refresh`, na wypadek gdyby watchdog już biegł.
- Jeśli M0+ nie zmieści się w czasie: podpis nad SHA-256 obrazu, jak w MCUboot.

Czytnik ediphor wchodzi w ship mode przez reset programowy i budzi się resetem.
Każde uśpienie i wybudzenie przechodzi więc przez weryfikację, a wybudzenie z przycisku wydłuża się o jej czas.

### Rozmiar

Bootloader dziś: G0 3,7kB w regionie 8kB, WB 6,9kB w regionie 16kB.
Z Ed25519 szacunkowo G0 ~18-20kB, WB ~24kB, do zmierzenia.

Region `key` jest większy niż `plain`, więc `FLASH_ORIGIN` i sloty różnią się między trybami.
Zmiana trybu to relink, Forge robi to sam, jak przy zmianie `PRO_BOOT`.
Tabela chipów: `boot_kB` dla `plain`, `boot_key_kB` dla `key`, oba ustalone raz na zawsze.

### Hex w Core

- `projects/boot/<hal>` to zwykły projekt z `PRO_BOOT false`, `make dist` daje hex.
- Jeden projekt, przełącznik `BOOT_KEY` w `main.h`, dwa produkty: `boot_<hal>.hex` i `boot_<hal>_key.hex`.
  `<hal>` to rodzina z tabeli chipów Forge: `stm32g0` dla G081 i G0C1, `stm32wb` dla WB55.
  Jeden bootloader na rodzinę, jak dziś `scr/boot_stm32g0.bin`.
- Core `scr/` trzyma oba hexy zamiast `.bin`, hex niesie adres, `0x08000000` znika z makefile.
- Forge poznaje nowy format po hexie w `scr/`.
  Stare Core ma tylko `.bin`: Forge kładzie go pod `FLASH_BASE`, trailera aplikacji nie rusza, a `PRO_BOOT_KEY` odmawia.

### `boot.c`

- Nagłówek `{magic, size, origin, chip, epoch}`, `size` i `origin` z linkera, `epoch` z `PRO_BOOT_EPOCH`.
- `BOOT_Begin` przyjmuje opcjonalny podpis, `BOOT_End` wpisuje trailer: CRC jak dziś, podpis albo `0xFF`.
- `BOOT_ImageValid`: nagłówek, `chip`, `origin`, CRC, a z `BOOT_KEY` także podpis kluczem z bootloadera.
  Klucz `0xFF` znaczy, że nic nie jest ważne.
- `BOOT_Install`: weryfikuje staging przed kopią, w `key` także `epoch` względem slotu, kopiuje `size` + 72B, weryfikuje slot po kopii, zostawia wynik w RAM.
- `BOOT_Status`: `image_crc` zostaje, dochodzi fingerprint klucza, `rdp` i ostatni wynik.
- Krypto kompilowane tylko z `BOOT_KEY`, aplikacja i bootloader `plain` nie widzą go wcale.
- Linker: `.app_trailer` 72B zamiast 8B, 8 bajtów RAM na wynik w `stm32g0.ld`.

## 8. Forge, makefile i debugger

### Forge

Jeden prymityw: mapa adres → bajt.
Wczytać hex albo bin pod adres, ustawić bajty, zapisać hex.
CRC, podpis, klucz i sklejenie z bootloaderem to ta sama operacja.

`-p --pack <app.hex> <out>` kończy obraz flasha.
To jedno polecenie dla wszystkich trybów: makefile nie wie, który jest w użyciu, Forge czyta go z `main.h`.

| Tryb | Trailer | Bootloader w hexie | Pliki w `build/` |
| --- | --- | --- | --- |
| bez bootloadera | nietknięty | brak | `-flash.hex`, kopia aplikacji |
| `plain` | CRC | `boot_<hal>.hex` | `-flash.hex`, `-update.bin` |
| `key` | CRC i podpis | `boot_<hal>_key.hex` z wpisanym kluczem | `-flash.hex`, `-update.bin` |

- W `key` build podpisuje kluczem deweloperskim i ten sam klucz wpisuje do bootloadera.
- Odmawia, gdy aplikacja wchodzi na region bootloadera albo wychodzi poza slot.
- Dziury wewnątrz obrazu aplikacji, np. między tablicą wektorów a nagłówkiem pod `0x200`, wypełnia `0xFF`.
  Hex zostawia je skasowane, a `.bin` z `objcopy` ma tam zera, więc bez tego CRC i podpis zależałyby od drogi.
- Rekord startu w hexie to adres tego, co rusza po resecie: bootloadera albo aplikacji.
- Krótkie `-p`, bo `-m` to już `--memory`.

Pozostałe:

- `dist`: w `key` powtarza `--pack` z kluczem produktu po haśle, potem kopiuje `-flash.hex` i `-update.bin` do projektu.
  Konwencja: ta sama nazwa, `.hex` to pełny obraz dla programatora, `.bin` sam obraz dla aktualizacji.
  Konsola ediphor bierze obraz z hexa spod adresu slotu z `boot info`, nie nagłówek spod `0x200` od początku pliku.
  Wtedy każdy hex działa jako aktualizacja: z dista, z builda, pełny albo sam obraz aplikacji.
  Czytanie od początku wysłałoby bootloader, bo pełny obraz zaczyna się od niego, a on też ma nagłówek `OPEN`.
  Hex bez bajtów pod adresem slotu konsola odrzuca.
- `--program <plik>`: wgrywa dowolny hex przez openocd, np. plik z `dist`.
- `--lock`, `--keygen <name>`: opisane wyżej.

Podpis bez zależności: własne ~60 linii Ed25519 według RFC 8032 w jednym module `keys.py`, hasło przez `hashlib.scrypt` ze stdlib.

- Szybkość wystarcza: podpis obrazu 250kB to kilka milisekund, bo hash liczy `hashlib` w C, a krzywa to kilkaset operacji na dużych liczbach.
- Poprawność: Ed25519 jest deterministyczny, więc wektory z RFC 8032 sprawdzają podpis co do bajtu.
  Łapią też złe liczenie nonce, najgroźniejszy cichy błąd, który zdradziłby klucz.
- Do tego weryfikacja krzyżowa z Monocypherem skompilowanym na host, patrz [Testy](#9-testy).
- Plik klucza: sól i seed XOR wynik `scrypt` z hasła, obok klucz publiczny.
  Złe hasło daje inny klucz publiczny, więc Forge rozpozna je od razu.
- Zero nowych zależności i zero licencji do dołączania, kod na licencji MIT jak Forge.

### `STM32_Programmer_CLI`

Openocd nie obsługuje FUS ani stacku radiowego CPU2 w WB, więc `make stack` potrzebuje CubeProgrammera.
Dziś `flash_cpu2.sh` szuka go w PATH i kończy się błędem, gdy go tam nie ma.

- Nie dołączamy go do pakietu, bo ST wydaje go po zalogowaniu i akceptacji licencji.
- Forge szuka zainstalowanego CubeProgrammera w domyślnej lokalizacji i dopisuje jego `bin` do PATH samej reguły `stack`.
  Skrypt w Core zostaje bez zmian, więc działa to też na starych wersjach Core.
- Ścieżka trafia do makefile dosłownie, przez `ProgramW6432`.
  32-bitowy make widzi `%ProgramFiles%` jako `Program Files (x86)`, a uruchomiony z Git Bash jako `PROGRAMFILES`.
- Nie ma go: Forge mówi wprost, żeby pobrać i zainstalować CubeProgrammer ze strony ST, i daje link.
- Dotyczy tylko `make stack`, a flash, debug i `--lock` zostają na openocd.

### Makefile

Jedna ścieżka i zero wiedzy o bootloaderze, trybie i kluczu:

```make
$(BUILD)/$(TARGET)-flash.hex: $(BUILD)/$(TARGET).hex
	@cd $(WORKSPACE) && $(FORGE) --pack $< $@
```

- `ARTIFACTS += $(BUILD)/$(TARGET)-flash.hex`.
- `flash` zawsze robi `program $(BUILD)/$(TARGET)-flash.hex verify reset exit`.
  Znika `ifeq ($(BOOT),true)`, `BOOT_BIN` i `0x08000000`.
- `dist` woła Forge, bo tylko Forge wie, co wysłać i jakim kluczem podpisać.
- `-update.bin` powstaje obok jako efekt uboczny, make o nim nie wie.

### Debugger

Debugger to nasza przewaga nad Zephyrem z MCUboot: jedno F5, bez osobnego buildu bootloadera, bez `west sign`, bez innego układu do debugowania niż do produkcji.

**`launch.json` ładuje `-flash.hex`, elf zostaje do symboli.**
Cortex-Debug ma na to `loadFiles` obok `executable`.

- Świeża płytka debuguje się od pierwszego F5, bez osobnego `make flash`.
- `launch.json`, jak makefile, nie wie nic o trybie ani bootloaderze.
- Układ i ścieżka startu są te same co w produkcji, różni się tylko klucz.
- `symbolFiles` pozwala nieść oba elfy w jednej sesji i przejść krokiem przez `BOOT_Jump` do aplikacji.

> **Uwaga:** `--lock` nigdy nie jest częścią `make flash` ani F5.

## 9. Testy

Bootloadera nie da się poprawić w polu, więc testy są częścią planu, nie dodatkiem.

- `boot.c` na platformie host, `hal/host` ma już `flash.c`.
  Instalacja z przerwą zasilania wstrzykniętą przed każdym zapisem flash: po restarcie slot jest stary albo nowy, nigdy pół na pół.
- Epoka: niższa odrzucona, równa i wyższa przyjęte, pusty slot przyjmuje każdą.
- Forge: wektory z RFC 8032, a podpis z Forge weryfikowany kodem bootloadera skompilowanym na host.
- Kompatybilność na sprzęcie: stary bootloader i nowy obraz, nowy bootloader i stary obraz, `UPDATE` ze starego firmware nowym narzędziem hosta.
- Sprzęt: czas startu G0 i WB, WB ze stackiem CPU2 po RDP1, `--lock` i zejście do RDP0.

## 10. Otwarte

Rozstrzygnięte, decyzje z uzasadnieniem są w [note.md](note.md).

## 11. Co zostało

### Wydanie 0.4.6

Gotowe w kodzie, zostaje wydanie:

- `--pack` wypełnia region bootloadera `0xFF` do początku slotu, więc każde wgranie kasuje rekord mailboxa,
- `make flash`, `make erase` i `--program` biorą jedno polecenie openocd z `openocd_command`,
- `--program` podaje ścieżkę w klamrach, więc spacje nie rozbijają jej na słowa.

### Tryb `key` w jednym ciągu

Całość powstaje na osobnej gałęzi Core i wychodzi jednym wydaniem Core i Forge, po testach end-to-end.
Testy na hoście rosną razem z kodem i biegną przy każdej zmianie.
Forge podpisuje, bootloader skompilowany na hosta weryfikuje i instaluje, zanik zasilania trafia przed każdy zapis, a każde odrzucenie ma właściwy kod.
Sprzęt wchodzi dwa razy: wczesna próba na G0 i testy end-to-end na końcu.

1. **Format obrazu**, jednocześnie w Core i Forge:
   - nagłówek `{magic, size, origin, chip, epoch}` pod `0x200`,
   - trailer 72B: CRC i miejsce na podpis,
   - wynik instalacji w słowie RAM, `stm32g0.ld` rezerwuje 8 bajtów jak `stm32wb.ld`,
   - `--pack` zapisuje nowy trailer.
2. **`boot.c`**:
   - oba tryby sprawdzają `chip` i `origin`: bootloader przy starcie, `BOOT_End` w aplikacji przed resetem,
   - pod `BOOT_KEY` podpis Monocypherem w kawałkach z `IWDG_Refresh` i epoka przy instalacji,
   - weryfikacja liczy przy 64MHz, a przed skokiem bootloader przywraca zegar do stanu po resecie,
   - `BOOT_Begin` przyjmuje podpis, `BOOT_End` zapisuje cały trailer,
   - `boot info` pokazuje odcisk klucza, `rdp` i wynik ostatniej instalacji.
3. **Wczesna próba na Nucleo-G0**: bootloader `key` z Monocypherem i obraz podpisany skryptem.
   Sprawdza start, czas weryfikacji i zapas stosu, a wynik zastępuje szacunek w note.md.
4. **Bootloader jako projekt w Core**: `projects/boot/<hal>` z przełącznikiem `BOOT_KEY`, a `make dist` daje `boot_<hal>.hex` i `boot_<hal>_key.hex` do `scr/`.
5. **Forge, tryb `key`**:
   - `PRO_BOOT_KEY` i `PRO_BOOT_EPOCH` w `main.h`,
   - klucz deweloperski Forge tworzy sam, klucz produktu jest szyfrowany hasłem przez `scrypt`, oba leżą w `%LOCALAPPDATA%/OpenCPLC/keys`,
   - `--keygen <produkt>` tworzy albo podpina klucz i sam wpisuje go do `main.h`,
   - ten sam pomocnik zmienia `PRO_VERSION` na `PRO_FRAMEWORK`, bo to wersja frameworka, a nie projektu, i tak nazywa ją Forge: `Framework version`, flaga `-f`.
     Przy reloadzie zmienia nazwę w projektach, a Forge przez jakiś czas przyjmuje starą,
   - `--pack` podpisuje kluczem deweloperskim i wpisuje go do bootloadera, a `dist` pyta o hasło i podpisuje kluczem produktu,
   - hex bootloadera pochodzi z nowego Core, ze starym Core działa tylko `plain`, a `PRO_BOOT_KEY` kończy się odmową,
   - testy: wektory z RFC 8032 i podpis z Forge sprawdzany kodem bootloadera skompilowanym na hoście.
6. **Konsola ediphor**: wysyła podpis w `begin`, przed wysłaniem porównuje `origin` obrazu z `boot info` i pokazuje powód, gdy bootloader odrzuci obraz.
7. **`--lock`**:
   - przez SWD czyta klucz z bootloadera na płytce i odmawia, gdy to nie `PRO_BOOT_KEY`,
   - po pytaniu `[YES/NO]` ustawia WRP na stronach bootloadera bez strony mailboxa, a potem jednym zapisem wyłącza `BOOT0` i włącza RDP1,
   - na WB ostrzega, że potem `make stack` nie zadziała,
   - konsola ostrzega, gdy urządzenie z kluczem produktu nie jest zablokowane.
8. **Testy end-to-end na sprzęcie**, skryptem na podłączonych Nucleo G0 i WB:
   - `make flash`, aktualizacja z konsoli plikiem `.bin` i `.hex`, odrzucenia, reset w trakcie instalacji, `boot info` i czas startu,
   - `--lock` i zejście do RDP0,
   - WB ze stackiem po `--lock`: BLE działa, stack przeżywa zejście do RDP0, a option bytes CPU2 zostają nietknięte,
   - zgodność: stary bootloader `plain` instaluje nowy obraz, a nowy bootloader czysto odrzuca stary,
   - aktualizacja ze starego firmware nowym narzędziem hosta.
9. **Wydanie Core i Forge**, potem pierwszy produkt wychodzi jako `key`.
