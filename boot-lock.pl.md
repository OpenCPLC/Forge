# 🥾 Bootloader i 🔒 blokada

Dwa niezależne mechanizmy.
Bootloader z Core decyduje, który obraz się uruchomi, i przyjmuje aktualizacje bez programatora.
Blokada zamyka port programatora i start z ROM.
Każdy działa bez drugiego, a razem dają poziom produkcyjny opisany w części Bezpieczeństwo.
Podstawy Forge są w [readme](readme.pl.md).

## 🥾 Bootloader

### Tryby

| | `plain` | `key` |
| --- | --- | --- |
| Uruchamia | obraz z poprawnym CRC | obraz podpisany kluczem produktu |
| Region bootloadera | 8kB na G0, 16kB na WB | 32kB |
| Koszt | nic | mniejszy slot, dłuższy start, klucz do pilnowania |
| Dla kogo | prototypy, nauka | produkt, który przyjmuje aktualizacje |

`plain` chroni tylko przed wypadkami: przerwaną albo uszkodzoną aktualizacją, zanikiem zasilania, plikiem dla innego urządzenia.
Nie jest bezpieczną konfiguracją produktu.

Za bootloaderem Forge dzieli resztę `PRO_FLASH_kB` na dwa równe sloty: slot aplikacji i staging, do którego najpierw trafia aktualizacja.
Bootloader kopiuje do slotu aplikacji tylko cały, sprawdzony obraz, więc przerwany transfer albo zanik zasilania w trakcie kopiowania nie szkodzi: działa stary obraz albo kopiowanie powtarza się przy następnym starcie.
`key` sprawdza do tego przy każdym starcie podpis Ed25519 kluczem, który nosi w swoim kodzie.

### Klucze

- **Klucz deweloperski** Forge robi sam przy pierwszym buildzie `key`, jeden na maszynę, jako `dev.key`.
  Podpisują nim `make`, `make flash` i F5, a ten sam klucz trafia do bootloadera, więc płytka na biurku przyjmuje własne buildy.
- **Klucz produktu** robi `--keygen`: `acme.key` zaszyfrowany hasłem i `acme.pub` obok.
  Podpisuje nim tylko `make dist`, po podaniu hasła.

Klucze leżą w `%LOCALAPPDATA%/OpenCPLC/keys`, na Linuksie w `~/.local/share/OpenCPLC/keys`, a `OPENCPLC_KEYS` wskazuje inny katalog.
Uszkodzony `dev.key` przenieś gdzie indziej, Forge zrobi nowy.

> [!WARNING]
> Utrata klucza produktu albo hasła kończy aktualizacje wszystkich urządzeń w polu, a wyciek pozwala każdemu podpisać obraz, który przyjmą.
> Trzymaj `acme.key` i hasło w dwóch kopiach offline, z ograniczonym dostępem, i miej osobny klucz dla każdego produktu.

### Włączenie

```sh
opencplc -n myapp -b uno -B  # nowy projekt z PRO_BOOT true w main.h
make run                     # build, potem bootloader i obraz przez ST-Link
```

Istniejący projekt przełącza jedna linia w `main.h`, `#define PRO_BOOT true`, a `make run` sam go przeładuje, bo `main.h` jest nowszy niż `makefile`.
Powrót to `PRO_BOOT false` i znowu `make run`, które nadpisuje bootloader zwykłym obrazem.

### Klucz produktu

```sh
opencplc myapp --keygen acme  # nowy klucz: hasło dwa razy, PRO_BOOT_KEY i PRO_BOOT_EPOCH 0 do main.h
make run                      # bootloader key z kluczem deweloperskim i podpisany obraz
```

Drugi projekt tego samego produktu bierze istniejący klucz, bez hasła:

```sh
opencplc panel --keygen acme
```

Projekt, który ma już `PRO_BOOT_KEY`, nowego klucza nie dostanie, bo odciąłby urządzenia w polu.

### Codzienna praca

```sh
make      # build, podpis kluczem deweloperskim
make run  # build i flash
```

Build daje `build/projects/myapp/myapp-dist.hex`, bootloader z obrazem w jednym pliku, który wgrywają `make flash` i F5, a obok `myapp-dist.bin`, sam obraz do aktualizacji.
F5 ma symbole bootloadera obok aplikacji, więc debugger przechodzi krokami z bootloadera do aplikacji.
Aktualizację na płytce deweloperskiej testuje ten `myapp-dist.bin`, bo obraz z `make dist` niesie podpis klucza produktu i płytka odrzuci go z `signature`.

### Wydanie

```sh
make dist TAG=1.2.0 # pod key pyta o hasło klucza acme
```

Do `projects/myapp/` trafia pełny obraz `myapp-1.2.0.hex` dla programatora i `myapp-1.2.0.bin` do aktualizacji, pod `key` oba z podpisem klucza produktu.
W CI klucz i hasło przychodzą ze zmiennych:

```sh
export OPENCPLC_KEYS=/secure/keys # acme.key i acme.pub
export OPENCPLC_KEY_PASSWORD=...
opencplc myapp
make dist TAG=1.2.0
```

Bez `acme.key` na maszynie `make dist` odmawia z `no private key for ...`, a przy złym haśle z `wrong password for key acme`, w obu przypadkach bez żadnego pliku.
Gdy `PRO_BOOT_KEY` to klucz deweloperski, `make dist` podpisze nim bez hasła: tak sprawdza się ścieżkę wydania, zanim powstanie klucz produktu.

Wydanie z łatką bezpieczeństwa podnosi epokę:

```sh
# w main.h: #define PRO_BOOT_EPOCH 1
make dist TAG=1.2.1
```

Po jego instalacji urządzenie nie przyjmie już obrazu z epoką 0, więc nie cofnie się do wersji z luką.
Epoka rośnie tylko z łatką, bo ma blokować powrót za granicę luki, a nie każdy powrót do starszej wersji, np. po nieudanym wydaniu.

### Aktualizacja

Aplikacja odbiera `myapp-1.2.0.bin` swoim łączem, np. BLE, RS albo USB, i oddaje bajty do `BOOT_Begin`, `BOOT_Write` i `BOOT_End` z `hal/stm32/sys/boot.h`, a podpis do `BOOT_Signature`.
`BOOT_End` sprawdza obraz tak jak bootloader, płytka się resetuje, a bootloader kopiuje obraz do slotu aplikacji i go uruchamia.
Kto może rozpocząć aktualizację i czy łącze jest szyfrowane, decyduje aplikacja.
Stos radiowy STM32WB też aktualizuje aplikacja: przyjmuje binarkę ST swoim łączem i zleca instalację FUS, a bootloader stosu nie dotyka.
Aplikacja powinna ruszać też bez stosu i dalej przyjmować aktualizacje przez USB, bo zanik zasilania w trakcie instalacji zostawia CPU2 bez stosu: `WPAN_Start` zwraca wtedy `ERR`, a kopia w stagingu pozwala instalację dokończyć.

Odrzucona aktualizacja zostawia działającą poprzednią wersję, a `boot info` podaje powód w `result`:

- `installed`: nowy obraz zainstalowany, `none` gdy start był bez aktualizacji
- `crc`: obraz uszkodzony
- `chip`: obraz na inny układ
- `origin`: obraz pod inny slot, np. zbudowany pod `plain` dla bootloadera `key`
- `signature`: podpis innym kluczem albo brak podpisu
- `epoch`: epoka niższa niż obrazu, który działa

Obok są `mode` (`plain` albo `key`), `key` z pierwszymi bajtami klucza bootloadera i `rdp` z poziomem blokady.

Do testów transfer idzie konsolą: `#define CMD_BOOT ON` w `main.h` dokłada komendę `boot`, a po stronie komputera wysyła `Shell.boot` z pakietu `xaeian`:

```py
from xaeian.serial import Shell

with Shell("COM5", strip_echo=False) as sh:
  sh.boot("projects/myapp/myapp-1.2.0.bin") # .hex też
```

### Kasowanie

```sh
make erase  # kasuje też bootloader
make stack  # STM32WB, stos radiowy, kasuje też bootloader
make flash  # bootloader i obraz z powrotem
```

Bez bootloadera albo z pustym slotem płytka nie uruchamia aplikacji, a wyjścia zostają w stanie po resecie: czy to bezpieczne dla maszyny, zależy od projektu płytki.

### Przebudowa bootloadera

Potrzebna po zmianie w Core plików, które wykonuje bootloader: `hal/stm32/sys/boot.c`, sterowniki flasha, CRC i zegara, `startup.c`, Monocypher pod `key` oraz `wpan_wb.c` na WB.
`make dist` zapisuje ten sam hex dla tego samego kodu, więc hex niezmieniony w `git status` Core znaczy, że przesunął się tylko elf z liniami źródeł, po których krokuje F5.
Projekt bootloadera ma w `main.h` `#define BOOT_KEY OFF` albo `ON`, a region kodu liczy Forge:

```sh
opencplc boot/stm32g0  # projekt bootloadera
make dist              # scr/boot_stm32g0.hex, z BOOT_KEY ON scr/boot_stm32g0_key.hex
```

Hex i elf trafiają do `scr/` w Core, a aplikacje pakują się z nowym bootloaderem przy następnym `make`.

## 🔒 Blokada

`--lock` ustawia przez SWD opcje chipu:

- RDP1: debugger i programator tracą dostęp do flasha, a zdjęcie blokady kasuje cały flash
- start z bootloadera ST w ROM wyłączony, cokolwiek mówi pin `BOOT0`
- pod bootloaderem także ochrona zapisu jego stron, bez strony mailboxa

Blokada nie zależy od trybu bootloadera: działa pod `plain`, pod `key` i bez bootloadera.
Nie sprawdza też, co płytka trzyma, tylko chip na sondzie, bo opcje różnią się między rodzinami.
Zawartość płytki ustala `--program`, dlatego w fabryce oba idą jednym wywołaniem.

| | `--lock`, RDP1 | `--lock 2`, RDP2 |
| --- | --- | --- |
| Debugger | odcięty, `--lock 0` kasuje flash i go oddaje | odcięty na zawsze |
| Ochrona zapisu bootloadera | zdejmie ją luka w aplikacji, przestawiając option bytes | zamrożona |
| Analiza uszkodzonej sztuki w ST | możliwa | niemożliwa |
| Stos radiowy na WB | `make stack` przed blokadą | tylko FUS z aplikacji |

### Fabryka

```sh
opencplc myapp
opencplc --program projects/myapp/myapp-1.2.0.hex --lock     # pełny obraz z dist, potem RDP1
opencplc --program projects/myapp/myapp-1.2.0.hex --lock -y  # linia produkcyjna, bez pytania
```

Pod `key` wgrywa się obraz z `make dist`: build z `make run` niesie klucz deweloperski, a sztuka z nim przyjęłaby aktualizacje tylko z maszyny dewelopera.
Po blokadzie `make flash`, F5 i `--program` nie dochodzą już do flasha, aktualizacje dalej przechodzą łączem aplikacji, a `boot info` pokazuje `rdp:1`.
Przy kilku ST-Linkach `opencplc myapp -s <serial>` wiąże właściwy z projektem, inaczej `--lock` trafi na obcy chip i odmówi.

Na STM32WB stos radiowy idzie przed obrazem, bo `make stack` używa SWD i kasuje bootloader:

```sh
make stack
opencplc --program projects/myapp/myapp-1.2.0.hex --lock
```

> [!NOTE]
> Po blokadzie wyłącz zasilanie całkiem i włącz je znowu, bo układ zablokowany przy podłączonym debuggerze nie uruchomi aplikacji.
> Adapter USB-UART na pinach konsoli potrafi zasilać układ, więc odłącz też jego, a na Nucleo przełóż zworkę zasilania na `CHG`.

### Blokada na zawsze

```sh
opencplc --program projects/myapp/myapp-1.2.0.hex --lock 2
```

> [!WARNING]
> RDP2 nieodwracalnie wyłącza port programatora, także dla producenta.
> Sztuki nie da się już odblokować, przeprogramować ani zbadać debuggerem, zostają tylko aktualizacje łączem aplikacji.

Forge pyta drugi raz, także z `-y`.
RDP2 dostaje tylko produkt, którego klient albo norma wymaga niezmienialnego bootloadera.

### Serwis

```sh
opencplc myapp
opencplc --lock 0  # zdejmuje blokadę, kasując cały flash
make flash         # bootloader i obraz z powrotem
```

Po `make flash` wyłącz zasilanie całkiem, bo STM32G0 po skasowaniu flasha startuje z ROM aż do pełnego restartu.
STM32WB zdejmuje blokadę przez STM32CubeProgrammer, ten sam, którego wymaga `make stack`, a kasowanie trwa kilka sekund.
Razem z blokadą znika cały flash, więc analiza sztuki z pola opiera się na logach zebranych wcześniej.

## 🛡️ Bezpieczeństwo

Bootloader odpowiada za to, **co** się uruchamia: podpis, CRC i epokę, sprawdzane przy każdym starcie.
Blokada odpowiada za to, czy da się bootloader ominąć: port programatora, start z ROM i ochronę zapisu bootloadera.
Aplikacja odpowiada za to, **kto** i **jak** przesyła aktualizację: dostęp do łącza, uwierzytelnienie, np. parowanie, i szyfrowanie.

Szyfrowanie zostaje w aplikacji, bo bootloadera się nie zmienia, więc klucza ani algorytmu nie dałoby się w nim wymienić.
Podpis liczony jest z jawnej treści, więc bootloader i tak sprawdzi wynik rozszyfrowania, a staging leży w wewnętrznej pamięci pod blokadą.
Jeden klucz szyfrowania na produkt, odczytany z jednej rozebranej sztuki, otwiera jednak wszystkie pliki aktualizacji, więc czy i jak szyfrować, decyduje producent.

✅ chroni, ❌ nie chroni, ⚠️ częściowo.

| Zagrożenie | `plain` | `plain` + `--lock` | `key` | `key` + `--lock` |
| --- | :---: | :---: | :---: | :---: |
| Przerwana albo uszkodzona aktualizacja | ✅ | ✅ | ✅ | ✅ |
| Zanik zasilania w trakcie instalacji | ✅ | ✅ | ✅ | ✅ |
| Aktualizacja dla innego urządzenia | ✅ | ✅ | ✅ | ✅ |
| Obce oprogramowanie przez łącze aktualizacji | ❌ | ❌ | ✅ | ✅ |
| Wersja deweloperska przez aktualizację na sztuce produkcyjnej | ❌ | ❌ | ✅ | ✅ |
| Powrót do starej wersji ze znaną luką | ❌ | ❌ | ✅¹ | ✅¹ |
| Obce oprogramowanie wgrane programatorem | ❌ | ✅ | ❌ | ✅ |
| Skopiowanie oprogramowania z urządzenia | ❌ | ✅ | ❌ | ✅ |
| Start z bootloadera ST w ROM (pin `BOOT0`) | ❌ | ✅ | ❌ | ✅ |
| Nadpisanie bootloadera przez błąd w aplikacji | ❌ | ✅ | ❌ | ✅ |
| Trwałe przejęcie przez lukę w działającej aplikacji | ❌ | ❌ | ❌ | ⚠️² |
| Poznanie treści oprogramowania z pliku aktualizacji³ | ❌ | ❌ | ❌ | ❌ |
| Ataki sprzętowe: zakłócanie zasilania, pomiar poboru prądu | ❌ | ❌ | ❌ | ❌ |

¹ Gdy lukę zamknęło wydanie z podniesioną epoką.
² Luka, która wykonuje obcy kod, może przestawić option bytes i zdjąć ochronę zapisu bootloadera, a zamraża je dopiero RDP2.
³ Poufność to zadanie aplikacji.

Projekt bez bootloadera z blokadą chroni przed programatorem, skopiowaniem i startem z ROM, a aktualizacji po prostu nie ma.

Celowo nie ma:

- **aktualizacji bootloadera w polu**, bo przerwana podmiana zostawiłaby martwe urządzenie, więc błąd w bootloaderze naprawia serwis,
- **odwołania klucza**, bo klucz siedzi w niezmiennym bootloaderze, więc szkody ogranicza osobny klucz na produkt,
- **sprzętowej strefy ochronnej**, bo STM32G0 ją ma, a STM32WB nie, a jedna droga dla obu rodzin jest prostsza do sprawdzenia,
- **automatycznej blokady przy pierwszym starcie**, bo każdy test wydania na płytce kończyłby się kasowaniem flasha,
- **watchdoga w bootloaderze**, bo koliduje z trybami uśpienia, więc aplikacja włącza go sama.

Unijny akt o cyberodporności (CRA), norma IEC 62443-4-2 dla komponentów automatyki, a dla urządzeń radiowych dyrektywa RED z normami EN 18031 oczekują między innymi autentycznego oprogramowania, bezpiecznych aktualizacji i zamkniętych interfejsów serwisowych:

| Oczekiwanie | Gotowe | Po stronie producenta |
| --- | --- | --- |
| Tylko autentyczne oprogramowanie | podpis sprawdzany przy każdym starcie | ochrona klucza produktu |
| Bezpieczne aktualizacje | podpis, odporność na zanik zasilania, raport wyniku | kto może rozpocząć aktualizację, wydawanie poprawek |
| Ochrona przed cofnięciem wersji | epoka | podniesienie epoki z każdą łatką |
| Zamknięte interfejsy serwisowe | `--lock`: port programatora i `BOOT0` | blokada każdej sztuki przed wysyłką |
| Bezpieczna konfiguracja fabryczna | `key` i `--lock`, każde jedną komendą | `key` + `--lock` dla produktu |
| Poufność oprogramowania | brak w bootloaderze | szyfrowanie w aplikacji, jeśli wymagane |
| Obsługa podatności | poza bootloaderem | zgłoszenia, poprawki, informowanie klientów |

> [!NOTE]
> Ten dokument nie jest deklaracją zgodności.
> Pokazuje, w czym mechanizmy pomagają, a które regulacje obejmują produkt, ustala producent.
