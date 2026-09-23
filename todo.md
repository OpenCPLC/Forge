# Bootloader z podpisem - plan

Cel: nikt nie wgra do sterownika obrazu, którego nie podpisaliśmy.
Ani przez `UPDATE` (BLE, RS, USB), ani przez programator.
Mechanizm ma być najprostszy z możliwych: dwa tryby, jeden format, jedno miejsce sprawdzania.

Stan dziś: obraz ma nagłówek `{magic, size}` pod `0x200` i 4-bajtowy CRC32 za obrazem, który urządzenie dopisuje przy stage'owaniu.
Programator zostawia trailer skasowany i bootloader to akceptuje.
Sprawdzana jest wyłącznie integralność transferu, tożsamości obrazu nikt nie pyta.

To notatka do przemyślenia, nie zadanie na dziś.
Nic z tego nie jest zrobione.

---

## 1. Dwa tryby

| | `plain` | `key` |
| --- | --- | --- |
| Bootloader | dzisiejszy, bez krypto | z Ed25519, klucz publiczny w środku |
| Flash | jak dziś: G0 8kB, WB 16kB | więcej, do zmierzenia, pewnie 16-24kB na G0 |
| Sprawdza podpis | nigdy | zawsze, przy każdym starcie |
| Bez klucza w bootloaderze | to jest jego stan | odmawia wszystkiego |
| Dla kogo | dev, hobby, domyślnie z pudełka | produkcja, razem z RDP1 |

Tryb wybiera `"key"` w `opencplc.json`: `null` to `plain`, nazwa klucza to `key`.
Forge dobiera do tego bootloader i układ pamięci.
Poza tym nic się nie zmienia: ten sam nagłówek, mailbox, transfer, `make flash`, `make dist`, F5.

`plain` to dzisiejszy bootloader i dzisiejsze rozmiary.
Nie płaci flashem za krypto, którego nie używa.

**W trybie `key` bootloader skacze tylko do obrazu z ważnym podpisem, przy każdym starcie.**
Nie „przy instalacji”, nie „raz i zapamiętaj”.
Nie ma stanu „zweryfikowany” do przechowywania, więc nic nie może się rozjechać.
Obraz z programatora podlega temu samemu co obraz z `UPDATE`.

> **Nota:** Bootloader `key` bez wpisanego klucza (32B `0xFF`) nie startuje niczego, czeka na SWD.
> Nie ma trybu „keyed, ale przepuszcza”, bo to byłaby druga droga do `plain`, tylko przez pomyłkę.

## 2. Co podpis chroni

Podpis zamyka drogę `UPDATE`.
Drogi programatora nie zamyka: kto ma SWD, może wgrać bootloader `plain`.
Tę drogę zamyka wyłącznie RDP.

- RDP1: debugger nie czyta i nie pisze flasha, zejście do RDP0 kasuje wszystko.
  Odwracalne, ale kosztem zawartości.
  To poziom na produkcję.
- RDP2: nieodwracalne, debugger martwy na zawsze.
  Raczej nie.

> **Uwaga:** Bez RDP podpis jest teatrem.
> W dokumentacji wprost: `key` + RDP1 = zamknięte urządzenie, samo jedno z nich = nic.

Do sprawdzenia na STM32WB: option bytes a FUS i stack CPU2, czy RDP1 nie psuje `make stack`.

## 3. Format obrazu

Dziś: `[wektory][nagłówek @0x200 {magic, size}][kod][CRC32]`, `size` liczy bajty przed CRC.

Docelowo: `[wektory][nagłówek @0x200 {magic, size}][kod][podpis 64B]`

- `size` liczy bajty przed podpisem, nagłówek zostaje bez zmian.
- Podpis Ed25519 nad bajtami `[0, size)`, więc wektory i nagłówek też pod podpisem.
- Podpis jest częścią pliku `.bin` i `.hex`, Forge dopisuje go przy buildzie.
  Urządzenie niczego nie dopisuje.
  Ten sam bajt w bajt trafia przez programator i przez `UPDATE`.
- W trybie `plain` Forge nie dopisuje nic, 64 bajty za `size` zostają skasowane.
  Obraz podpisany na bootloaderze `plain` też działa, trailer jest ignorowany.

Jeden format w obu trybach, podpis to opcjonalne 64B na końcu.

CRC32 znika z formatu flasha, zostaje w transferze.
`boot begin <size> <crc>` niesie długość pliku i CRC całego pliku.
`BOOT_End` liczy CRC nad stage'owanymi bajtami i porównuje.
Wykrycie przekłamania transportu zostaje tam, gdzie jest tanie i natychmiastowe.
Mailbox nie potrzebuje już `crc`, tylko `page` i `size` pliku.

Znika hack „skasowany trailer = OK”.
Slot jest ważny, gdy nagłówek się zgadza (`plain`) albo nagłówek i podpis się zgadzają (`key`).
Nic więcej.

Podpis sprawdza wyłącznie bootloader: nad slotem aplikacji przy starcie i nad stagingiem przed instalacją.
Aplikacja sprawdza w `BOOT_End` tylko CRC i rozmiar, krypto nie nosi w żadnym trybie.

Zły podpis wychodzi więc na jaw dopiero po resecie, w bootloaderze, cicho.
Mailbox dostaje pole `result`, aplikacja czyta je po starcie i mówi hostowi, dlaczego dalej jest stara wersja.
Jedno pole, jeden komunikat, bez drugiego miejsca weryfikacji.

## 4. Klucz

Para Ed25519: 32B seed prywatny, 32B klucz publiczny.

**Klucz publiczny mieszka w bootloaderze `key`, w stałym miejscu, wpisywany przez Forge.**
Core dostarcza bootloader `key` bez klucza, Forge wpisuje klucz użytkownika do hexa przy składaniu obrazu flasha.
Jeden bootloader `key` dla wszystkich, klucz to dane, nie kod.
Nikt nie buduje bootloadera sam.

Miejsce: sekcja `.boot_key` pod stałym offsetem, np. `0x208`, zaraz za nagłówkiem bootloadera.
Bootloader jako obraz Forge też ma `{magic, size}` pod `0x200`.
Stały offset, więc Forge wie, co łatać, bez czytania mapy linkera.

Klucz prywatny:

- `%LOCALAPPDATA%/OpenCPLC/keys/<name>.key`, nigdy w repo, nigdy w workspace.
- `opencplc --keygen <name>` tworzy parę i drukuje fingerprint.
- `opencplc.json` wskazuje `"key": "<name>"` i trzyma klucz publiczny w hex.
  Klon workspace wie, jakiego bootloadera oczekuje, nawet bez prywatnego.
- Forge z `"key"` bez pliku prywatnego odmawia buildu z `PRO_BOOT true`, głośno.
  Nie ma cichego „zbudowałem, ale bez podpisu”.

Praktyka zespołu: płytki deweloperskie `plain`, produkcja `key` z RDP1, klucz na jednej maszynie release.
Kto nie ma klucza, nie robi produkcji.

`boot info` raportuje `key: <fingerprint>`, `key: none` albo `key: missing` dla bootloadera `key` bez klucza.

## 5. Bootloader

### Krypto i rozmiar

Ed25519, bo weryfikacja nie potrzebuje RNG, podpis jest deterministyczny i nie ma pułapek z nonce.
Klucz 32B, podpis 64B, jedna sprawdzona implementacja, jeden plik.
To samo na M0+ i M4, bez PKA z WB55, żeby była jedna ścieżka kodu.

Kandydaci: Monocypher (czytelny, ~10-14kB thumb z SHA-512) albo c25519 (~6kB, wolniejszy).
Do zmierzenia na obu rdzeniach: rozmiar i czas weryfikacji obrazu 100kB.
Szacunek: 0,1-0,5s przy 16MHz, bootloader może podnieść zegar na czas liczenia.
Próg akceptacji to „start w pół sekundy”, nie „zero”.

Region `key` jest większy niż `plain`, więc `FLASH_ORIGIN` i sloty różnią się między trybami.
Zmiana trybu to relink, Forge robi to sam, jak przy zmianie `PRO_BOOT`.
Tabela chipów: `boot_kB` zostaje dla `plain`, dochodzi `boot_key_kB`.

Symetryczny HMAC odpada: klucz w bootloaderze czytany przez SWD zdradza go na każdym egzemplarzu.

### Hex w Core

- `projects/boot/<hal>` to zwykły projekt z `PRO_BOOT false`, `make dist` daje `boot_<hal>.hex`.
  Bootloader przestaje być czymś specjalnym.
- Jeden projekt, przełącznik `BOOT_KEY` w `main.h`, dwa produkty: `boot_<hal>.hex` i `boot_<hal>_key.hex`.
- Core `scr/` trzyma oba hexy zamiast `.bin`.
  Hex niesie adres, `0x08000000` znika z makefile.
- Stare wersje Core mają tylko `.bin`: Forge robi fallback `bin@FLASH_BASE` dla `plain`, a `key` odmawia.
  Stała zostaje w resolverze, gdzie już jest.

### `boot.c`

- `BOOT_ImageValid`: nagłówek, a z `BOOT_KEY` także podpis nad `[0, size)` kluczem z `.boot_key`.
  Klucz `0xFF` znaczy, że nic nie jest ważne.
  Bez CRC, bez „skasowany trailer = OK”.
- `BOOT_End`: CRC transferu nad stage'owanymi bajtami jak dziś, bez dopisywania trailera.
- Mailbox: `{magic, size, page, result}`, `crc` wypada.
- `BOOT_Install`: weryfikuje staging przed kopią, zapisuje `result` przy odmowie.
- `BOOT_Status`: `image_crc` wypada, dochodzi fingerprint klucza i ostatni `result`.
- Krypto kompilowane tylko z `BOOT_KEY`, czyli tylko do bootloadera `key`.
  Aplikacja i bootloader `plain` nie widzą go wcale.
- Linker: `.app_trailer` rezerwuje 64B zamiast 8B, `.boot_key` w obrazie bootloadera `key`.

Kompatybilność: obraz zbudowany starym Core ma CRC za `size`.
Bootloader `plain` ignoruje trailer, więc taki obraz startuje.
Bootloader `key` go odrzuca, słusznie.

## 6. Forge

Jeden prymityw: mapa adres → bajt.
Wczytać hex albo bin pod adres, ustawić bajty, zapisać hex.
Podpis, klucz, sklejenie z bootloaderem to ta sama operacja.

`-m <app.hex> <out>` kończy obraz flasha:

1. W trybie `key` podpisuje aplikację, dopisuje 64B za `size`.
2. Przy `PRO_BOOT true` wczytuje `scr/boot_<hal>.hex` albo `scr/boot_<hal>_key.hex`, w `key` wpisuje klucz publiczny pod `0x208`, dokłada aplikację.
3. Zapisuje `build/<target>-flash.hex` oraz `.bin` aplikacji dla `UPDATE`, w `key` z podpisem.

Pozostałe komendy:

- `--keygen <name>` tworzy parę, `--key` pokazuje fingerprint.
- `--lock` ustawia RDP1 przez openocd, tylko na wyraźne żądanie, z pytaniem `[YES/NO]`.

Biblioteka: `cryptography`.
Referencyjna implementacja w czystym Pythonie jest wolna (sekundy na podpis) i jest własnym krypto do utrzymania.
Zależność nic nie kosztuje, bo Forge jedzie jako exe z PyInstallera.
Klucze w formacie zgodnym z `openssl` i `ssh-keygen`.
Krypto siedzi w jednym module `keys.py`, importowanym leniwie tylko w trybie `key`.
Workspace `plain` nigdy tego kodu nie dotyka.

## 7. Makefile i debugger

Makefile ma jedną ścieżkę i zero wiedzy o bootloaderze i trybie:

```make
$(BUILD)/$(TARGET)-flash.hex: $(BUILD)/$(TARGET).hex
	@cd $(WORKSPACE) && $(FORGE) -m $< $@
```

- `ARTIFACTS += $(BUILD)/$(TARGET)-flash.hex`.
- `flash` zawsze robi `program $(BUILD)/$(TARGET)-flash.hex verify reset exit`.
  Znika `ifeq ($(BOOT),true)`, `BOOT_BIN` i `0x08000000`.
- `dist` kopiuje `-flash.hex` jako `<target>-1.2.0.hex` i `.bin` aplikacji jako `<target>-1.2.0.bin`.
  Dwa produkty, bo są dwie drogi: pierwsza instalacja i aktualizacja.
- Bez bootloadera flashujemy hex zamiast elf, dla openocd bez różnicy.

Forge decyduje o wszystkim z `main.h` i `opencplc.json`, jak dziś o rozmiarze przez `-z`.

Debugger to nasza przewaga nad Zephyrem z MCUboot: jedno F5, bez osobnego buildu bootloadera, bez `west sign`, bez innego layoutu do debugowania niż do produkcji.
Dziś [launch.json](opencplc/files/launch.json) ładuje przez gdb sam `.elf`, a bootloader musi już być we flashu.
W trybie `key` elf jest bez podpisu, bootloader odmawia i F5 kończy w `while(1)`.

**`launch.json` ładuje `-flash.hex`, elf zostaje do symboli.**
Cortex-Debug ma na to `loadFiles` obok `executable`.
`-flash.hex` jest artefaktem `make`, więc `preLaunchTask` daje zawsze świeży, podpisany, z bootloaderem w środku.

- Świeża płytka debuguje się od pierwszego F5, bez osobnego `make flash`.
- Bootloader we flashu jest zawsze zgodny z wersją Core projektu.
- `launch.json`, jak makefile, nie wie nic o trybie ani bootloaderze.
- To, co debugujesz, to bajt w bajt to, co idzie do produkcji.
- Weryfikacja przy resecie to 0,1-0,5s czekania na breakpoint w `main`.

Bootloader debuguje się jak każdy projekt: `opencplc -r boot/stm32g0`, F5.
`symbolFiles` pozwala nieść oba elfy w jednej sesji i przejść krokiem przez `BOOT_Jump` do aplikacji.
Dodatek, nie wymóg.

RDP1 to koniec debuggera, celowo i tylko na sztukach produkcyjnych.
Płytka deweloperska zostaje na RDP0 z tym samym bootloaderem `key` i tym samym obrazem.

> **Uwaga:** `--lock` nigdy nie jest częścią `make flash` ani F5.

## 8. Otwarte

- Anti-rollback: `version` w nagłówku, bootloader `key` odmawia niższej.
  Osobna polityka, ale format nagłówka zmienia się raz, więc zdecydować przed pkt 3.
- Tożsamość: `chip` albo `product` w nagłówku, żeby obraz G0 nie wylądował na WB przy jednym kluczu na wiele produktów.
  Alternatywa bez zmiany formatu: klucz per produkt.
- Wypełnianie stagingu `0xFF` w `-flash.hex`: stan po produkcji zdefiniowany, ale każde F5 kasuje 60kB więcej, a wypełnienie tylko w `dist` daje dist ≠ flash.
  Skłaniam się do: nie wypełniać, staging to sprawa bootloadera.
- Czas startu na G0 przy 16MHz: zmierzyć, zanim cokolwiek się zdecyduje.
- Reader: jak host dowiaduje się o odrzuceniu, pole `result` w `boot info` i `UPDATE`.
- Nazwa drugiego hexa: `_key`, `_sig`, `_secure`?
  Ma mówić „ten trzyma klucz”, nie „ten jest podpisany”.

## 9. Kolejność

1. Zmierzyć Ed25519 na G0 i WB: rozmiar i czas, wybrać implementację, ustalić `boot_key_kB`.
2. Format: nagłówek, `.app_trailer` 64B, mailbox z `result`. Jedna zmiana, jedna wersja Core.
3. `boot.c`: weryfikacja pod `BOOT_KEY`, `.boot_key`, `boot info`.
4. Bootloader jako projekt z `dist`, dwa hexy w `scr/`.
5. Forge: mapa hex, `-m` z wyborem trybu, `--keygen`, `"key"` w `opencplc.json`, fallback dla starych Core.
6. Makefile: jedna reguła, `-flash.hex`, `dist` z dwoma plikami; `launch.json` z `loadFiles`.
7. `--lock` i dokumentacja: „`key` + RDP1, albo nic”.
8. Reader: `result` z mailboxa do hosta.
