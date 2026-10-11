Najpierw odpowiedź na pytanie o Forge, potem plan. Niczego nie zmieniałem.

Forge i wybór układu: nie
Układ musi być wpisany w main.h jako PRO_CHIP_*. Bez tej linii Forge kończy z błędem „has no PRO_CHIP definition”. Flaga -c działa tylko przy tworzeniu projektu (-n). Przy istniejącym projekcie Forge jej odmawia (flags_reject) i każe zmienić PRO_CHIP_<CHIP> w main.h. Jedyny przełącznik na jeden przebieg to -f, czyli wersja Core.

W repo kilka układów rozwiązuje się osobnymi projektami: .tests/g081 i .tests/wb55, a w boot stm32g0-test i stm32wb-test. Te dwa ostatnie to prawie kopie, różnią się pinami UART i LED-em.

Propozycja: jeden projekt projects/test/flash zamiast test/ecc

projects/test/flash/
  main.c          konsola, UART płytki, komendy, raport przy starcie
  test_flash.c    sterownik i rekordy flash
  test_eeprom.c
  test_pdb.c
  flash_test.py   jedno polecenie: kasowanie, wgranie, wszystkie testy, werdykt
  readme.md       jak przejść testy na G0 i WB, co znaczą werdykty
Pliki i przypadki nazywają się jak w testach hosta (.tests/test_*.c). Ten sam kontrakt jest wtedy sprawdzony na modelu i na krzemie.

Katalog testów
Moduł	Funkcjonalne (nazwy jak na hoście)	Cięcia przez NRST (jak na hoście)	Tylko na krzemie
flash	record_loads_back_whole, shorter_record_replaces_longer, refuses_what_does_not_fit	save_survives_a_cut	Reguły, na których stoi model hosta (lista niżej)
eeprom	newest_value_wins, rewrites_keep_every_key, reserved_keys_refused, variables_come_back_by_address, clear_forgets_everything	write_survives_a_cut: pozostałe klucze nietknięte, klucz w trakcie zapisu ma starą albo nową wartość, brak zawieszeń	Zdarzenia ECC liczone
pdb	records_come_back_in_order, ring_keeps_the_newest_pages, queries_page_through_the_log	insert_survives_a_cut	Zdarzenia ECC liczone
Reguły modelu hosta do sprawdzenia na krzemie w module flash:

kasowanie daje 0xFF;
drugi zapis na zapisane słowo kończy się ERR bez zawieszenia;
zera da się zapisać na zapisane słowo;
wiersz idzie tylko do strony skasowanej ostatnio (G0);
na WB odczyt po zapisie i po kasowaniu zwraca nowe dane mimo pamięci podręcznej danych.
Host ma dwa warianty cięcia: przed cyklem i w połowie. Na krzemie NRST trafia w obie sytuacje, więc jeden test sprzętowy pokrywa oba. Sprawdzanie reguł modelu ma prosty powód: testy hosta są warte tyle, ile założenia modelu. Jedno potwierdzenie na każdy układ trzyma je w ryzach.

Jak to działa
Jeden obraz. Przy każdym starcie firmware sprawdza trzy magazyny, drukuje jedną linię i czeka na komendę skryptu (CMD_AddCommand):
func uruchamia testy funkcjonalne i drukuje OK|ERR <moduł>/<przypadek>;
cut eeprom|pdb|flash zaczyna pętlę zapisów tego magazynu i kręci nią aż do resetu.
Tryb na każdy start. Skrypt wybiera go przy każdym starcie, więc nic nie trzeba trwale zapisywać ani zmieniać w main.h.
Strony magazynów. Każdy magazyn ma własne strony, o numerach wspólnych dla G0 i WB, tak jak dzisiejsza strona 60.
Uruchomienie: py projects/test/flash/flash_test.py COM7 [cięcia]. Skrypt robi make erase, make run i func, potem N cięć na każdy magazyn. Werdykty wydaje jak lock_test.py, zwraca kod wyjścia i zapisuje log przebiegu.
Czas: testy funkcjonalne trwają kilka sekund. Jedno cięcie to około 0,35 s, więc 3 × 300 cięć zajmie około 5 minut, a 3 × 1000 około 18 minut.
Zakres: bootloader zostaje w projects/boot.
Do decyzji
Nazwy: projekt test/flash, skrypt flash_test.py, na wzór lock_test.py?
Wybór układu. Proponuję linię PRO_CHIP_* w main.h: bez kopii, a zmiana układu to jedna linia. Alternatywa to dopisać do Forge flagę -c na jeden przebieg, jak -f, ale to zmiana w Forge.
Harness na układzie. tst/test.h działa tylko na hoście (printf, setjmp, atexit). Proponuję mały check w projekcie, który wypisuje przez LOG. Backend tst na układ to zmiana w Core, warta zachodu dopiero przy kolejnych zestawach sprzętowych.
Liczba cięć. Domyślnie 300 na magazyn, a 1000 na życzenie?
Porządki:
stare logi cut-*.log proponuję usunąć, bo ich liczby są w plan-test-fixes.md;
projects/test/pdb i projects/test/core to testy hosta (PRO_CHIP_HOST), które dublują .tests w Core. Wycofanie ich to osobna decyzja.