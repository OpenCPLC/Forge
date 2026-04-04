## OpenCPLC ⚒️ Forge

**Forge** jest aplikacją konsolową usprawniającą pracę z **OpenCPLC**, którego zadaniem jest dostosowanie środowiska pracy tak, aby 👨‍💻programista-automatyk mógł skupić się na tworzeniu aplikacji, a nie walce z konfiguracją ekosystemu i kompilacją programu. Dostępny jest jako pakiet **Python [`pip`](https://pypi.org/project/opencplc)** lub jako samodzielny plik wykonywalny **`opencplc.exe`** z 🚀[Releases](https://github.com/OpenCPLC/Forge/releases) _(w tym przypadku należy ręcznie dodać jego lokalizację do zmiennych systemowych **PATH**)_

```sh
pip install opencplc
```

Po prostu w wybranej lokalizacji _(którą uznasz za workspace)_ odpal [CMD](#-console) i wpisz:

```sh
opencplc -n <project_name> -b <board>
opencplc -n myapp -b Uno
```

Wówczas w [lokalizacji z projektami](#️-config) `${projects}` tworzony jest katalog _(lub drzewo katalogów)_ zgodny z przekazaną nazwą `<project_name>`. Powstają w nim dwa pliki: `main.c` i `main.h`, które stanowią minimalny zestaw plików projektu. Nie można ich usuwać ani przenosić do podkatalogów.

Gdy będziemy mieli więcej projektów, będziemy mogli swobodnie przełączać się między nimi.

```sh
opencplc <project_name>
opencplc myapp
```

Projekty możemy też wybierać po numerze z listy:

```sh
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

```sh
opencplc <project_name>
opencplc -r
```

Tutaj _(upraszczając)_ kończy się zadanie programu **Forge**, a dalsza praca przebiega tak samo jak w typowym projekcie **embedded systems**, czyli przy użyciu [**✨Make**](#-make).

## ✨ Make

Jeżeli mamy poprawnie przygotowaną konfigurację projektu oraz plik `makefile` wygenerowany za pomocą programu ⚒️**Forge**, to aby zbudować i wgrać program na sterownik PLC, wystarczy otworzyć konsolę w przestrzeni roboczej _(workspace)_ i wpisać:

```sh
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
- **`pwsh`**: Wykrywany automatycznie. Wartość `true` wymusza przygotowanie pliku `makefile` w wersji dla powłoki **PowerShell**. Dla wartości `false` zostanie przygotowana wersja dla powłoki **Bash**.
- `available-versions`: Lista wszystkich dostępnych wersji framework'a. Jej zawartość jest ustawiana automatycznie.

## 🤔 How works?

W pierwszej kolejności **Forge** zainstaluje **GNU Arm Embedded Toolchain**, **OpenOCD**, **Make**, klienta **Git** oraz ustawi odpowiednio zmienne systemowe, jeżeli aplikacje nie są widoczne w systemie z poziomu konsoli. Dla platformy HOST zamiast toolchain'a ARM instalowany jest **MinGW** (GCC dla Windows). Jeżeli nie chcemy, aby ktoś grzebał w naszym systemie, możemy przygotować sobie [konfiguracje ręcznie](self-install.md). Gdy ⚒️**Forge** zainstaluje brakujące aplikacje, doda je do systemowego PATH i będzie kontynuować pracę. Po zakończeniu zrestartuj konsolę, aby korzystać z nich bezpośrednio.

Następnie, w razie konieczności, skopiuje framework OpenCPLC z [repozytorium](https://github.com/OpenCPLC/Core) do folderu `${framework}` podanego w pliku konfiguracyjnym `opencplc.json`. Zostanie sklonowana wersja z pliku konfiguracyjnego lub wskazana za pomocą `-f --framework`:

```sh
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

```sh
opencplc -n myapp -c Host # projekt desktopowy
```

Tworzy to projekt kompilowany natywnym GCC (MinGW na Windows) zamiast toolchain'a ARM. Przydatne do:

- Testowania algorytmów i logiki bez sprzętu
- Rozwijania parserów protokołów i przetwarzania danych
- Testów jednostkowych komponentów framework'a
- Szybkiego prototypowania przed wdrożeniem na PLC

Platforma HOST dostarcza stub'y dla modułów zależnych od sprzętu (GPIO, timery, itp.), więc struktura kodu pozostaje kompatybilna z targetami STM32.

## 🚩 Flags

#### Podstawowe

- **`name`**: Nazwa projektu, domyślny pierwszy argument. Wyznacza ścieżkę `${projects}/name` i jest powiązana z plikami wsadowymi (`.bin`, `.hex`, `.elf`). Można też podać numer z listy `-l`.
- `-n --new`: Tworzy nowy projekt o wskazanej nazwie.
- `-e --example`: Wczytuje przykład z repozytorium [Demo](https://github.com/OpenCPLC/Demo).
- `-r --reload`: Odczytuje nazwę projektu z istniejącego `makefile` i regeneruje pliki projektowe. Nie wymaga podania `name`.
- `-d --delete`: Usuwa projekt o wskazanej nazwie.
- `-g --get`: Pobiera projekt z GitHub/GitLab lub zdalnego ZIP i dodaje jako nowy. Drugi argument to referencja (`branch`, `tag`). Jeśli `name` nie podano, odczytuje go z `@name` w `main.h`.

#### Konfiguracja sprzętu

- `-b --board`: Model sterownika PLC: `Uno`, `Dio`, `Aio`, `Eco`, `Custom` lub `None` dla czystego mikrokontrolera. Tryb `Custom` udostępnia warstwę PLC bez gotowego mapowania peryferiów.
- `-c --chip`: Mikrokontroler lub platforma: `STM32G081`, `STM32G0C1`, `STM32WB55`, `HOST`. Bez `-b` projekt działa bez warstwy PLC, tylko HAL i biblioteki standardowe. Przydatne dla Nucleo lub własnego hardware.
- `-m --memory`: Pamięć w kB: `FLASH RAM [RESERVED]`. `RESERVED` zostaje odjęte od FLASH w pliku linkera `flash.ld`. _(tylko STM32)_

#### Konfiguracja kompilacji

- `-f --framework`: Wersja frameworka: `latest`, `develop`, `1.0.0`. Jeśli nie podano, odczytywana z `opencplc.json`.
- `-o --opt-level`: Poziom optymalizacji: `O0` _(debug)_, `Og` _(domyślny)_, `O1`, `O2`, `O3`. Poziomy `O2`/`O3` wyświetlają ostrzeżenie dla STM32, dozwolone dla `HOST`.

#### Informacje

- `-l --list`: Wyświetla listę projektów lub przykładów (z flagą `-e`).
- `-i --info`: Zwraca informacje o aktywnym projekcie, w tym wersje projektu i frameworka.
- `-F --framework-versions`: Wyświetla dostępne wersje frameworka OpenCPLC.
- `-v --version`: Wyświetla wersję ⚒️Forge i link do repozytorium.

#### Narzędzia

- `-a --assets`: Pobiera materiały pomocnicze _(dokumentacja, diagramy)_. Opcjonalnie przyjmuje nazwę folderu docelowego.
- `-u --update`: Sprawdza i instaluje aktualizacje ⚒️Forge. Można podać konkretną wersję lub `latest`.
- `-y --yes`: Automatycznie potwierdza wszystkie pytania _(tryb nieinteraktywny)_.

#### Hash utilities

- `-hl --hash-list`: Generuje enum z hashem DJB2 dla listy tagów.
- `-ht --hash-title`: Nazwa typu enum dla generatora hashy.
- `-hd --hash-define`: Używa `#define` zamiast `enum`.

🗑️ Usuwanie i 💾 kopiowanie projektów można wykonywać bezpośrednio z poziomu systemu operacyjnego.
Każdy projekt przechowuje wszystkie niezbędne informacje w pliku `main.h`, a jego obecność jest automatycznie wykrywana podczas uruchamiania programu.

## 📟 Console

Programy ⚒️Forge oraz ✨Make są programami uruchamianymi z konsoli CMD. Stanowią niezbędnik do pracy z OpenCPLC.

Konsola systemowa jest dostępna w wielu aplikacjach, takich jak **Command Prompt**, **PowerShell**, [**GIT Bash**](https://git-scm.com/downloads), a nawet terminal w [**VSCode**](https://code.visualstudio.com/). Gdy wywołanie w konsoli zwróci błąd, prawdopodobnie nie została otwarta w przestrzeni roboczej _(workspace)_. Możesz zamknąć konsolę i otworzyć ją w odpowiednim folderze lub przejść ręcznie, używając komendy `cd`.

## 📋 Przykłady użycia

```sh
# Tworzenie nowego projektu
opencplc -n myapp -b Uno                  # projekt dla sterownika OpenCPLC Uno
opencplc -n myapp -b Eco -m 128 36        # projekt dla Eco z pamięcią 128kB/36kB
opencplc -n myapp -b Custom -c STM32G081  # własny hardware z warstwą PLC (bez mapowania peryferiów)
opencplc -n myapp -c STM32G081            # projekt bare-metal dla STM32G081 (np. Nucleo)
opencplc -n myapp -c Host                 # projekt desktopowy (Windows/Linux)

# Zarządzanie projektami
opencplc myapp      # załaduj projekt 'myapp'
opencplc 3          # załaduj projekt #3 z listy
opencplc -r         # przeładuj aktywny projekt
opencplc -l         # lista wszystkich projektów
opencplc -i         # informacje o aktywnym projekcie

# Przykłady demonstracyjne
opencplc -e blinky  # załaduj przykład 'blinky'
opencplc -e -l      # lista dostępnych przykładów

# Pobieranie projektów
opencplc -g https://github.com/user/repo
opencplc -g https://github.com/user/repo v1.0.0

# Aktualizacje
opencplc -u         # aktualizuj Forge do najnowszej wersji
opencplc -F         # pokaż dostępne wersje Core
```