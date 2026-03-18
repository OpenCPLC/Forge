## OpenCPLC ⚒️ Forge

**Forge** jest aplikacją konsolową usprawniającą pracę z **OpenCPLC**, którego zadaniem jest dostosowanie środowiska pracy tak, aby 👨‍💻programista-automatyk mógł skupić się na tworzeniu aplikacji, a nie walce z konfiguracją ekosystemu i kompilacją programu. Dostępny jest jako pakiet **Python [`pip`](https://pypi.org/project/opencplc)** lub jako samodzielny plik wykonywalny **`opencplc.exe`** z 🚀[Releases](https://github.com/OpenCPLC/Forge/releases) _(w tym przypadku należy ręcznie dodać jego lokalizację do zmiennych systemowych **PATH**)_

```bash
pip install opencplc
```

Po prostu w wybranej lokalizacji _(którą uznasz za workspace)_ odpal [CMD](#-console) i wpisz:

```bash
opencplc -n <project_name> -b <board>
opencplc -n blinky -b Uno
```

Wówczas w [lokalizacji z projektami](#️-config) `${projects}` tworzony jest katalog _(lub drzewo katalogów)_ zgodny z przekazaną nazwą `<project_name>`. Powstają w nim dwa pliki: `main.c` i `main.h`, które stanowią minimalny zestaw plików projektu. Nie można ich usuwać ani przenosić do podkatalogów.

Gdy będziemy mieli więcej projektów, będziemy mogli swobodnie przełączać się między nimi.

```bash
opencplc <project_name>
opencplc blinky
```

Projekty możemy też wybierać po numerze z listy:

```bash
opencplc -l  # wyświetl listę projektów
opencplc 3   # załaduj projekt #3 z listy
```

Podczas tworzenia nowego projektu lub przełączania się na istniejący, generowane są na nowo wszystkie pliki _(`makefile`, `flash.ld`, ...)_ niezbędne do poprawnego przeprowadzenia procesu kompilacji, czyli przekształcenia całości _(plików projektu i framework'a: `.c`, `.h`, `.s`)_ w pliki wsadowe `.bin`/`.hex`, które można wgrać do sterownika jako działający program.

W przypadku zmiany wartości konfiguracyjnych `PRO_x` w pliku **`main.h`** lub modyfikacji **struktury projektu**, obejmującej:

- dodawanie nowych plików,
- przenoszenie plików,
- usuwanie plików,
- zmiany nazw plików,

niezbędne jest ponowne załadowanie projektu. Jeśli projekt jest już aktywny, nie trzeba podawać jego nazwy `-r --reload`:

```bash
opencplc <project_name>
opencplc -r
```

Tutaj _(upraszczając)_ kończy się zadanie programu **Forge**, a dalsza praca przebiega tak samo jak w typowym projekcie **embedded systems**, czyli przy użyciu [**✨Make**](#-make).

## ✨ Make

Jeżeli mamy poprawnie przygotowaną konfigurację projektu oraz plik `makefile` wygenerowany za pomocą programu ⚒️**Forge**, to aby zbudować i wgrać program na sterownik PLC, wystarczy otworzyć konsolę w przestrzeni roboczej _(workspace)_ i wpisać:

```bash
make build  # buduj projekt C do programu binarnego
make flash  # wgraj plik binarny do pamięci sterownika PLC
# lub
make run    # run = build + flash
```

Plik `makefile` udostępnia również kilka innych funkcji. Oto pełna lista:

- **`make build`** lub samo **`make`**: Buduje projekt w języku C do postaci plików wsadowych `.bin`, `.hex`, `.elf`
- **`make flash`**: Wgrywa plik wsadowy programu do pamięci sterownika PLC _(mikrokontrolera)_
- **`make run`**: Wykonuje `make build`, a następnie `make flash`
- **`make clean`** lub `make clr`: Usuwa zbudowane pliki wsadowe dla aktywnego projektu
- `make clean_all` lub `make clr_all`: Usuwa zbudowane pliki wsadowe dla wszystkich projektów
- `make dist`: Kopiuje pliki `.bin` i `.hex` do folderu projektu
- **`make erase`**: Całkowicie czyści pamięć mikrokontrolera _(**erase** full chip)_

## ⚙️ Config

Podczas pierwszego uruchomienia ⚒️Forge'a tworzony jest plik konfiguracyjny **`opencplc.json`**. Zawiera on:

- **`version`**: Domyślna wersja framework'a OpenCPLC. Wymuszana jest jej instalacja. Zastępuje nieokreśloną wersję `-f --framework`. Wartość `latest` oznacza najnowszą stabilną wersję.
- `paths`: Lista ścieżek _(względnych)_
  - `projects`: Główny katalog z projektami. Nowe projekty tworzone są w tym miejscu. Można też skopiować projekt ręcznie. Wszystkie projekty są wykrywane automatycznie. Nazwą projektu jest dalsza część tej ścieżki.
  - `examples`: Katalog z przykładami demonstracyjnymi pobieranymi z repozytorium [Demo](https://github.com/OpenCPLC/Demo).
  - `framework`: Katalog zawierający wszystkie wersje frameworka OpenCPLC. W jego wnętrzu tworzone są podkatalogi odpowiadające wersjom w formacie `major.minor.patch`, `develop` lub `main`. Każdy z nich zawiera pliki odpowiedniej wersji frameworka. Pobierane będą jedynie niezbędne wersje.
  - `build`: Katalog z zbudowanymi aplikacjami
- `default`: Lista domyślnych wartości _(`chip`, `flash`, `ram`, `optLevel`)_ dla nieprzekazanych parametrów podczas tworzenia nowego projektu
- **`pwsh`**: Ustawienie tego parametru na `true` wymusza przygotowanie pliku `makefile` w wersji dla powłoki **PowerShell**. Dla wartości `false` zostanie przygotowana wersja dla powłoki **Bash**.
- `available-versions`: Lista wszystkich dostępnych wersji framework'a. Jej zawartość jest ustawiana automatycznie.

## 🤔 How works?

W pierwszej kolejności **Forge** zainstaluje **GNU Arm Embedded Toolchain**, **OpenOCD**, **Make**, klienta **Git** oraz ustawi odpowiednio zmienne systemowe, jeżeli aplikacje nie są widoczne w systemie z poziomu konsoli. Dla platformy HOST zamiast toolchain'a ARM instalowany jest **MinGW** (GCC dla Windows). Jeżeli nie chcemy, aby ktoś grzebał w naszym systemie, możemy przygotować sobie [konfiguracje ręcznie](self-install.md). Gdy ⚒️**Forge** zainstaluje brakujące aplikacje, poprosi o zresetowanie konsoli, ponieważ zmienne systemowe są ładowane podczas jej uruchamiania, a w procesie instalacji zostały dodane nowe.

Następnie, w razie konieczności, skopiuje framework OpenCPLC z [repozytorium](https://github.com/OpenCPLC/Core) do folderu `${framework}` podanego w pliku konfiguracyjnym `opencplc.json`. Zostanie sklonowana wersja z pliku konfiguracyjnego lub wskazana za pomocą `-f --framework`:

```bash
opencplc <project_name> --new -f 1.0.2
opencplc <project_name> --new -f develop
```

### 📌 Wersjonowanie projektu

Każdy projekt przechowuje w pliku `main.h` wersję framework'a, na której został utworzony _(definicja `PRO_VERSION`)_. W przypadku przełączania się na istniejący projekt:

- Jeśli wersja projektu różni się od aktualnej wersji framework'a, **Forge** spróbuje pobrać odpowiednią wersję
- Jeśli pobranie się nie powiedzie, zostanie wyświetlone ostrzeżenie o potencjalnej niekompatybilności
- Przykłady demonstracyjne `-e --example` zawsze używają wersji zapisanej w projekcie

Dzięki temu mechanizmowi starsze projekty mogą być kompilowane nawet po aktualizacji framework'a do nowszej wersji.

Główną funkcją **Forge**'a jest przygotowanie plików niezbędnych do pracy z wybranym projektem:

- `flash.ld`: definiuje rozkład pamięci RAM i FLASH mikrokontrolera _(nadpisuje, tylko STM32)_
- `makefile`: Zawiera reguły budowania, czyszczenia i flashowania projektu _(nadpisuje)_
- `c_cpp_properties.json`: ustawia ścieżki do nagłówków i konfigurację IntelliSense w VS Code _(nadpisuje)_
- `launch.json`: konfiguruje debugowanie w VSCode _(nadpisuje)_
- `tasks.json`: opisuje zadania takie jak kompilacja czy flashowanie _(nadpisuje)_
- `settings.json`: ustawia lokalne preferencje edytora _(tworzy raz, nie nadpisuje)_
- `extensions.json`: sugeruje przydatne rozszerzenia do VSCode _(tworzy raz, nie nadpisuje)_

Istnieje także całkiem sporo funkcji pomocniczych, do których dostęp uzyskuje się za pomocą sprytnego wykorzystania [**🚩flag**](#-flags).

### 🗂️ Struktura workspace

```
workspace/
├─ opencplc.json  # konfiguracja workspace
├─ makefile       # aktywny projekt (generowany przez Forge)
├─ flash.ld       # linker script (generowany przez Forge, tylko STM32)
├─ .vscode/       # konfiguracja VSCode (generowana przez Forge)
├─ opencplc/      # framework (pobierany automatycznie)
│  ├─ 1.0.3/
│  ├─ 1.2.0/
│  └─ develop/
├─ projects/      # projekty użytkownika
│  ├─ myapp/
│  │  ├─ main.c
│  │  └─ main.h
│  └─ firm/app/   # projekty mogą być zagnieżdżone
│     ├─ main.c
│     └─ main.h
├─ examples/      # przykłady demonstracyjne
└─ build/         # skompilowane pliki wsadowe
```

Jeśli IntelliSense przestanie działać poprawnie, użyj `F1` → _C/C++: Reset IntelliSense Database_.

## 🖥️ Host

Forge wspiera platformę **Host** do rozwijania i testowania kodu na PC (Windows/Linux) bez sprzętu embedded:

```bash
opencplc -n myapp -c Host # projekt desktopowy
```

Tworzy to projekt kompilowany natywnym GCC (MinGW na Windows) zamiast toolchain'a ARM. Przydatne do:

- Testowania algorytmów i logiki bez sprzętu
- Rozwijania parserów protokołów i przetwarzania danych
- Testów jednostkowych komponentów framework'a
- Szybkiego prototypowania przed wdrożeniem na PLC

Platforma HOST dostarcza stub'y dla modułów zależnych od sprzętu (GPIO, timery, itp.), więc struktura kodu pozostaje kompatybilna z targetami STM32.

## 🚩 Flags

Oprócz podstawowych flag opisanych powyżej, istnieje jeszcze kilka, które mogą pozostać niezmienione, ale warto znać ich istnienie. Poniżej znajduje się lista wszystkich flag:

### Podstawowe

| Flaga | Opis |
|-------|------|
| **`name`** | Nazwa projektu. Parametr domyślny przekazywany jako pierwszy. Będzie również stanowić ścieżkę do projektu: `${projects}/name`, a końcowe pliki wsadowe _(`.bin`, `.hex`, `.elf`)_ będą z nią ściśle skorelowane. Można też podać numer projektu z listy `-l`. |
| `-n --new` | Tworzy nowy projekt o wskazanej nazwie. |
| `-e --example` | Wczytuje przykład demonstracyjny o wskazanej nazwie z repozytorium [Demo](https://github.com/OpenCPLC/Demo). |
| `-r --reload` | Pobiera nazwę projektu oraz określa, czy jest to przykład, na podstawie wcześniej wygenerowanego pliku `makefile`, a następnie generuje pliki projektowe na nowo. Wówczas nie jest wymagane podawania nazwy **`name`**. |
| `-d --delete` | Usuwa wybrany projekt ze wskazaną nazwą **`name`**. |
| `-g --get` | Pobiera projekt z serwisu GIT _(**GitHub**, **GitLab**, ...)_ lub zdalnego pliku ZIP i dodaje go jako nowy. Jako drugi argument _(pierwszym jest link)_ można przekazać referencję _(`branch`, `tag`)_. Jeśli nie została określona nazwa projektu **`name`**, zostanie podjęta próba odczytania jej z pola `@name` z pliku `main.h`. |

### Konfiguracja sprzętu

| Flaga | Opis |
|-------|------|
| `-b --board` | Model sterownika PLC dla nowego projektu: `Uno`, `Dio`, `Aio`, `Eco`, `Custom` dla własnej konstrukcji lub `None` dla pracy z czystym mikrokontrolerem. Tryb `Custom` udostępnia warstwę PLC, ale bez gotowego mapowania peryferiów: konfigurację należy uzupełnić samodzielnie. |
| `-c --chip` | Mikrokontroler lub platforma: `STM32G081`, `STM32G0C1`, `STM32WB55`, `HOST` (kompilacja na PC). Gdy podany bez `-b --board`, projekt działa bez warstwy PLC: dostępny jest wyłącznie HAL i biblioteki standardowe frameworka. Przydatne przy pracy z płytkami Nucleo lub własnym hardware. |
| `-m --memory` | Ilość pamięci w kB: `FLASH RAM [RESERVED]`. Parametr `RESERVED` określa pamięć zarezerwowaną na konfigurację i EEPROM, która zostanie odjęta od FLASH w pliku linkera `flash.ld`. _(tylko STM32)_ |

### Konfiguracja kompilacji

| Flaga | Opis |
|-------|------|
| `-f --framework` | Wersja framework'a: `latest`, `develop`, `1.0.0`. Jeśli nie zostanie podana, zostanie odczytana z pola `version` w pliku konfiguracyjnym `opencplc.json`. |
| `-o --opt-level` | Poziom optymalizacji kodu dla kompilacji: `O0` _(debug)_, `Og` _(domyślny)_, `O1`, `O2`, `O3`. Poziomy `O2`, `O3` wyświetlają ostrzeżenie dla STM32 _(problemy z timingiem/debugowaniem)_, ale są dozwolone dla HOST. |

### Informacje

| Flaga | Opis |
|-------|------|
| `-l --list` | Wyświetla listę istniejących projektów lub przykładów, gdy aktywna jest flaga `-e --example`. |
| `-i --info` | Zwraca podstawowe informacje o wskazanym lub aktywnym projekcie, w tym wersję projektu i framework'a. |
| `-F --framework-versions` | Wyświetla wszystkie dostępne wersje framework'a OpenCPLC. |
| `-v --version` | Wyświetla wersję programu ⚒️Forge oraz link do repozytorium. |

### Narzędzia

| Flaga | Opis |
|-------|------|
| `-a --assets` | Pobiera materiały pomocnicze przydatne podczas projektowania _(dokumentacja, diagramy)_. Jako wartość można przekazać nazwę folderu, w którym paczka zostanie umieszczona. |
| `-u --update` | Sprawdza dostępność aktualizacji i aktualizuje program ⚒️Forge. Można podać konkretną wersję lub `latest`. |
| `-y --yes` | Automatycznie potwierdza wszystkie pytania _(tryb nieinteraktywny)_. |

### Hash utilities

| Flaga | Opis |
|-------|------|
| `-hl --hash-list` | Generuje enum z hashem DJB2 dla listy tagów. |
| `-ht --hash-title` | Nazwa typu enum dla generatora hash'y. |
| `-hd --hash-define` | Używa `#define` zamiast `enum` dla wyjścia hash'y. |

🗑️Usuwanie i 💾kopiowanie projektów można oczywiście wykonywać bezpośrednio z poziomu systemu operacyjnego.
Każdy projekt przechowuje wszystkie niezbędne informacje o sobie w pliku `main.h`, a jego obecność jest automatycznie wykrywana podczas uruchamiania programu.

## 📟 Console

Programy ⚒️Forge oraz ✨Make są programami uruchamianymi z konsoli CMD. Stanowią niezbędnik do pracy z OpenCPLC.

Konsola systemowa jest dostępna w wielu aplikacjach, takich jak **Command Prompt**, **PowerShell**, [**GIT Bash**](https://git-scm.com/downloads), a nawet terminal w [**VSCode**](https://code.visualstudio.com/). Gdy wywołanie w konsoli zwróci błąd, prawdopodobnie nie została otwarta w przestrzeni roboczej _(workspace)_. Możesz zamknąć konsolę i otworzyć ją w odpowiednim folderze lub przejść ręcznie, używając komendy `cd`.

## 📋 Przykłady użycia

```bash
# Tworzenie nowego projektu
opencplc -n myapp -b Uno                  # Projekt dla sterownika OpenCPLC Uno
opencplc -n myapp -b Eco -m 128 36        # Projekt dla Eco z pamięcią 128kB/36kB
opencplc -n myapp -b Custom -c STM32G081  # Własny hardware z warstwą PLC (bez mapowania peryferiów)
opencplc -n myapp -c STM32G081            # Projekt bare-metal dla STM32G081 (np. Nucleo)
opencplc -n myapp -c Host                 # Projekt desktopowy (Windows/Linux)
# Zarządzanie projektami
opencplc myapp      # Załaduj projekt 'myapp'
opencplc 3          # Załaduj projekt #3 z listy
opencplc -r         # Przeładuj aktywny projekt
opencplc -l         # Lista wszystkich projektów
opencplc -i         # Informacje o aktywnym projekcie
# Przykłady demonstracyjne
opencplc -e blinky  # Załaduj przykład 'blinky'
opencplc -e -l      # Lista dostępnych przykładów
# Pobieranie projektów
opencplc -g https://github.com/user/repo
opencplc -g https://github.com/user/repo v1.0.0
# Aktualizacje
opencplc -u         # Aktualizuj Forge do najnowszej wersji
opencplc -F         # Pokaż dostępne wersje framework'a
```