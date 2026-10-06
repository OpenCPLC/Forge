ENTRY(Reset_Handler)

_estack = ORIGIN(RAM) + LENGTH(RAM);

_Min_Heap_Size = 0x200;
_Min_Stack_Size = 0x400;

/* RAM opens with 8 bytes no image owns: the bootloader leaves its report there */
MEMORY
{
  RAM(xrw)        : ORIGIN = 0x20000008, LENGTH = ${RAM}K - 8
  FLASH(rx)       : ORIGIN = ${FLASH_ORIGIN}, LENGTH = ${FLASH}K
  RAM_SHARED(xrw) : ORIGIN = 0x20030000, LENGTH = 10K
}

_boot_report = ORIGIN(RAM) - 8;

SECTIONS
{
  .isr_vector : {
    . = ALIGN(4);
    KEEP(*(.isr_vector))
    . = ALIGN(4);
  } >FLASH

  /* Image header at a fixed offset, read by the bootloader and the update tool */
  .app_header ORIGIN(FLASH) + 0x200 : {
    KEEP(*(.app_header))
  } >FLASH

  .text : {
    . = ALIGN(4);
    *(.text)
    *(.text*)
    *(.glue_7)
    *(.glue_7t)
    *(.eh_frame)
    KEEP (*(.init))
    KEEP (*(.fini))
    . = ALIGN(4);
    _etext = .;
  } >FLASH

  .rodata : {
    . = ALIGN(4);
    *(.rodata)
    *(.rodata*)
    . = ALIGN(4);
  } >FLASH

  .ARM.extab : {
    *(.ARM.extab* .gnu.linkonce.armextab.*)
  } >FLASH

  .ARM : {
    __exidx_start = .;
    *(.ARM.exidx*)
    __exidx_end = .;
  } >FLASH

  .preinit_array : {
    PROVIDE_HIDDEN (__preinit_array_start = .);
    KEEP (*(.preinit_array*))
    PROVIDE_HIDDEN (__preinit_array_end = .);
  } >FLASH

  .init_array : {
    PROVIDE_HIDDEN (__init_array_start = .);
    KEEP (*(SORT(.init_array.*)))
    KEEP (*(.init_array*))
    PROVIDE_HIDDEN (__init_array_end = .);
  } >FLASH

  .fini_array : {
    PROVIDE_HIDDEN (__fini_array_start = .);
    KEEP (*(SORT(.fini_array.*)))
    KEEP (*(.fini_array*))
    PROVIDE_HIDDEN (__fini_array_end = .);
  } >FLASH

  _sidata = LOADADDR(.data);

  .data : {
    . = ALIGN(4);
    _sdata = .;
    *(.data)
    *(.data*)
    *(.RamFunc)
    *(.RamFunc*)
    . = ALIGN(4);
    _edata = .;
  } >RAM AT> FLASH

  . = ALIGN(4);

  .bss : {
    _sbss = .;
    __bss_start__ = _sbss;
    *(.bss)
    *(.bss*)
    *(COMMON)
    . = ALIGN(4);
    _ebss = .;
    __bss_end__ = _ebss;
  } >RAM

  ._user_heap_stack : {
    . = ALIGN(8);
    PROVIDE ( end = . );
    PROVIDE ( _end = . );
    . = . + _Min_Heap_Size;
    . = . + _Min_Stack_Size;
    . = ALIGN(8);
  } >RAM

  /DISCARD/ : {
    libc.a ( * )
    libm.a ( * )
    libgcc.a ( * )
  }

  .ARM.attributes 0       : { *(.ARM.attributes) }
   MAPPING_TABLE (NOLOAD) : { *(MAPPING_TABLE) } >RAM_SHARED
   MB_MEM1 (NOLOAD)       : { *(MB_MEM1) } >RAM_SHARED

  _siMB_MEM2 = LOADADDR(.MB_MEM2);

  .MB_MEM2 : {
    _sMB_MEM2 = . ;
    *(MB_MEM2) ;
    _eMB_MEM2 = . ;
  } >RAM_SHARED AT> FLASH

  /* End of the image, the value of its header. Behind it 72 erased bytes of trailer:
     the CRC32 at their start, the Ed25519 signature a doubleword further.
     Symbols set inside a section are section-relative unless made `ABSOLUTE`. */
  .app_trailer : {
    . = ALIGN(8);
    _image_size = ABSOLUTE(. - ORIGIN(FLASH));
    FILL(0xFFFFFFFF);
    LONG(0xFFFFFFFF);
    . += 72 - 4;
  } >FLASH

  /* Key of a `key` bootloader, the last bytes of its code region where Forge writes it.
     Any other image has no such section, so nothing moves. */
  .boot_key ORIGIN(FLASH) + LENGTH(FLASH) - 32 : {
    KEEP(*(.boot_key))
  } >FLASH
}
