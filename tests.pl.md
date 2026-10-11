# 🧪 Testy

Testy biegną na komputerze, także w projekcie STM32, i sprawdzają sam kod firmware'u, a nie jego kopię.
`make test` buduje każdy program z `.tests/` i uruchamia go, a jeden plik workflow robi to samo na GitHubie przy każdym pushu.
Podstawy Forge są w [readme](readme.pl.md).

## Program testowy

Każdy plik `.c` bezpośrednio w `.tests/` w katalogu głównym projektu to jeden program testowy, domyślnie `test_<moduł>.c` od modułu, który sprawdza.
`.tests/` nie leży nigdy głębiej, więc od razu widać, że to nie część firmware'u.

```text
myapp/
├─ main.c
├─ main.h
├─ ctrl/ramp.c
└─ .tests/
   ├─ test_ramp.c  # program testowy modułu ramp
   ├─ fake/link.c  # podróbka modułu link, nie program
   └─ data/        # stałe wejścia i oczekiwane wartości, w repo
```

Test dołącza moduł, który sprawdza, po samej nazwie, `#include "ramp.c"`, bo moduły mają jedną płaską przestrzeń nazw, tak jak w firmware.
Wykonuje więc kod firmware'u, także funkcje `static`.
Kompiluje się tylko to, co dołączył, więc rejestry w innych miejscach projektu nigdy nie przeszkadzają.
`main()` daje harness, więc `main.c` nigdy nie wchodzi do testu.

Żaden program nie nosi nazwy modułu: cudzysłów szuka najpierw obok pliku, więc `.tests/ramp.c` zastąpiłby moduł w każdym teście.
Przedrostek `test_` to najprostsze wyjście, ale pasuje każda nazwa, której nie ma żaden moduł.

```c
// .tests/test_ramp.c

#include "test.h"
#include "ramp.c"

static void ramp_starts_at_zero(void)
{
  RAMP_t ramp = { .target = 100, .step = 30 };
  TEST_Equal(ramp.value, 0, "value before the first step");
}

static void ramp_stops_at_target(void)
{
  RAMP_t ramp = { .target = 100, .step = 30 };
  for(int i = 0; i < 5; i++) RAMP_Step(&ramp);
  TEST_Equal(ramp.value, 100, "no overshoot");
}

void TEST_Cases(void)
{
  TEST(ramp_starts_at_zero);
  TEST(ramp_stops_at_target);
}
```

- `TEST_Cases()` wymienia przypadki w kolejności wykonania, po jednym `TEST(name)`.
- `TEST_Check(cond)` albo `TEST_Check(cond, fmt, ...)` to werdykt, a `TEST_Equal`, `TEST_Near` i `TEST_Bytes` przy chybieniu pokazują wyrażenie tak, jak je napisano, jego wartość i oczekiwaną.
- `TEST_Logged(text)`: firmware zalogował linię z `text` od początku przypadku albo od poprzedniego `TEST_Logged`.
- `TEST_Run(ms)` robi `ms` kroków czasu wirtualnego, a krok to tick w przód i każde należne zadanie.

## Uruchamianie

```sh
make test              # wszystkie programy z `.tests/`
make test T=test_ramp  # tylko `.tests/test_ramp.c`, z jego wyjściem
```

Każdy program startuje we własnym czystym katalogu i dostaje linię z udanymi sprawdzeniami na tle wszystkich, a przebieg kończy się sumą:

```text
INF test_frame 12/12 OK
INF test_ramp 2/2 OK
INF Test programs 2/2, checks 14/14 in 0.2s OK
```

Program, który zawiódł, pokazuje pod swoją linią swoje wyjście tak, jak je wypisał.
Chybienie podaje plik i linię oraz wyrażenie z wartością, kończy swój przypadek, a dalej biegnie następny:

```text
INF test_frame 12/12 OK
ERR test_ramp 1/2
OK ramp_starts_at_zero
ERR projects/myapp/.tests/test_ramp.c:16 ramp_stops_at_target: no overshoot
  ramp.value is 150, expected 100
ERR Test programs 1/2, checks 13/14 in 0.5s
```

Z `T=` program pokazuje swoje wyjście także wtedy, gdy przechodzi.
Program, który skończy się przed czasem, to błąd, także przez `exit(0)` resetu firmware'u, a zawieszony Forge ucina po minucie.
`make test` przechodzi przez wszystkie programy i kończy się błędem, gdy któryś zawiódł.
Nowy plik w `.tests/` nie wymaga przeładowania.

## Zasady

- Czekanie przesuwa zegar: `delay()` i `timeout()` robią kroki czasu wirtualnego, więc test timeoutu nie trwa ani chwili.
  `sleep()` trzyma rdzeń, więc czas płynie, a żadne zadanie nie rusza.
- Moduł, który woła testowany kod, wchodzi tak samo albo jako podróbka całego modułu z podkatalogu `.tests/`, `#include "fake/link.c"`, bo podróbka nosi nazwę swojego modułu.
  Przy podróbce części modułu Core linker dociągnąłby oryginał z archiwum i zdublował resztę.
- Stałe wejścia i oczekiwane wartości, np. nagrana ramka albo podpis zrobiony przez Forge, leżą w `data/` i też przychodzą po katalogu, `#include "data/forge.h"`.
  Pisze się je ręcznie albo skryptem obok i commituje, a przebieg nic tam nie zapisuje: to, co program zapisze, zostaje w jego czystym katalogu pod `build/`.
- `#define` przed `#include` może stroić dołączany moduł, np. `LOG_LEVEL`.
  Rozmiar albo typ wspólny z resztą Core, np. `BUFF_MSG_LIMIT`, należy do `main.h`, bo inaczej test i Core po cichu się rozjadą.
- Core wchodzi do testu skompilowany z `hal/host`, `lib` i `tst`, a ich moduły test dołącza po nazwie.
  Moduł z `plc/`, `brd/`, `dvr/` albo `hal/stm32*` przychodzi po ścieżce od korzenia Core, np. `#include "hal/stm32/sys/boot.c"`.
- Projekt STM32 z testami dostaje MinGW obok `arm-gcc`.

## GitHub

Repozytorium projektu uruchamia `make test` i `make` przy każdym pushu jednym plikiem:

```yaml
# .github/workflows/test.yml
name: Test
on: [push, pull_request]
jobs:
  test:
    uses: OpenCPLC/Forge/.github/workflows/project.yml@0.5.0
```

Robi to, co Ty w świeżym workspace, dla każdego projektu w repozytorium, na Windowsie z narzędziami Forge.
Core przychodzi z `PRO_FRAMEWORK`, jak na Twoim komputerze.
Tag przypina wydanie Forge, więc nowy Forge nigdy nie zmieni wyniku sam z siebie.

> [!NOTE]
> W prywatnym repozytorium przebiegi zużywają darmowe minuty planu, a minuta Windowsa kosztuje więcej niż Linuksa.

## Core

Core testuje się tak samo, z `.tests/` w swoim katalogu głównym:

```text
opencplc/develop/.tests/
├─ test_boot.c   # program testowy modułu boot
├─ test_cron.c
├─ data/forge.h  # klucz i podpis zrobione przez Forge, z forge.py
├─ g081/         # projekt: test kompilacji STM32G081
├─ g0c1/
├─ wb55/
└─ uno/          # projekt: warstwa PLC na płytce Uno
```

Plik `.c` bezpośrednio w `.tests/` to program testowy, katalog z `main.h` to projekt, a każdy inny katalog pomaga testom, np. `fake/` i `data/`.
Core nie trzyma atrap, bo jego modelem układu jest `hal/host`: tamtejszy flash kasuje, programuje i traci zasilanie jak układ, a test odcina to zasilanie przez `FlashBudget`.

```sh
opencplc opencplc/develop              # sam Core
make test                              # jego programy testowe
opencplc opencplc/develop/.tests/g081  # test kompilacji
make                                   # buduje go
```

GitHub przy każdym pushu i pull requeście robi `make` w każdym projekcie z `.tests/` i `make test` Core.
Nowy moduł albo poprawka błędu przychodzi z testem, który go sprawdza, a nowy chip albo płytka z projektem w `.tests/`.
