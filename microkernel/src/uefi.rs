//! Minimal, auditable UEFI 2.10 ABI bindings for x86_64 bare-metal boot.
//! No Linux, no Windows, no std, no external crates.

#![allow(dead_code)]

use core::ffi::c_void;

pub type Status = usize;
pub type Handle = *mut c_void;

pub const EFI_SUCCESS: Status = 0;

#[repr(C)]
#[derive(Clone, Copy)]
pub struct Guid {
    pub data1: u32,
    pub data2: u16,
    pub data3: u16,
    pub data4: [u8; 8],
}

pub const GRAPHICS_OUTPUT_PROTOCOL_GUID: Guid = Guid {
    data1: 0x9042a9de,
    data2: 0x23dc,
    data3: 0x4a38,
    data4: [0x96, 0xfb, 0x7a, 0xde, 0xd0, 0x80, 0x51, 0x6a],
};

#[repr(C)]
pub struct TableHeader {
    pub signature: u64,
    pub revision: u32,
    pub header_size: u32,
    pub crc32: u32,
    pub reserved: u32,
}

#[repr(C)]
pub struct SystemTable {
    pub hdr: TableHeader,
    pub firmware_vendor: *const u16,
    pub firmware_revision: u32,
    pub console_in_handle: Handle,
    pub con_in: *mut c_void,
    pub console_out_handle: Handle,
    pub con_out: *mut c_void,
    pub standard_error_handle: Handle,
    pub std_err: *mut c_void,
    pub runtime_services: *mut c_void,
    pub boot_services: *mut BootServices,
    pub number_of_table_entries: usize,
    pub configuration_table: *mut c_void,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct MemoryDescriptor {
    pub typ: u32,
    pub pad: u32,
    pub physical_start: u64,
    pub virtual_start: u64,
    pub number_of_pages: u64,
    pub attribute: u64,
}

pub const EFI_CONVENTIONAL_MEMORY: u32 = 7;

#[repr(C)]
pub struct BootServices {
    pub hdr: TableHeader,
    // Task Priority Services (2)
    pub raise_tpl: *const c_void,
    pub restore_tpl: *const c_void,
    // Memory Services (5)
    pub allocate_pages: *const c_void,
    pub free_pages: *const c_void,
    pub get_memory_map: unsafe extern "efiapi" fn(
        memory_map_size: *mut usize,
        memory_map: *mut MemoryDescriptor,
        map_key: *mut usize,
        descriptor_size: *mut usize,
        descriptor_version: *mut u32,
    ) -> Status,
    pub allocate_pool: *const c_void,
    pub free_pool: *const c_void,
    // Event & Timer Services (6)
    pub create_event: *const c_void,
    pub set_timer: *const c_void,
    pub wait_for_event: *const c_void,
    pub signal_event: *const c_void,
    pub close_event: *const c_void,
    pub check_event: *const c_void,
    // Protocol Handler Services (9)
    pub install_protocol_interface: *const c_void,
    pub reinstall_protocol_interface: *const c_void,
    pub uninstall_protocol_interface: *const c_void,
    pub handle_protocol: *const c_void,
    pub reserved: *const c_void,
    pub register_protocol_notify: *const c_void,
    pub locate_handle: *const c_void,
    pub locate_device_path: *const c_void,
    pub install_configuration_table: *const c_void,
    // Image Services (5)
    pub load_image: *const c_void,
    pub start_image: *const c_void,
    pub exit: *const c_void,
    pub unload_image: *const c_void,
    pub exit_boot_services: unsafe extern "efiapi" fn(image_handle: Handle, map_key: usize) -> Status,
    // Misc Services (3)
    pub get_next_monotonic_count: *const c_void,
    pub stall: *const c_void,
    pub set_watchdog_timer: unsafe extern "efiapi" fn(
        timeout: usize,
        watchdog_code: u64,
        data_size: usize,
        watchdog_data: *const u16,
    ) -> Status,
    // DriverSupport Services (2)
    pub connect_controller: *const c_void,
    pub disconnect_controller: *const c_void,
    // Open and Close Protocol Services (3)
    pub open_protocol: *const c_void,
    pub close_protocol: *const c_void,
    pub open_protocol_information: *const c_void,
    // Library Services (4)
    pub protocols_per_handle: *const c_void,
    pub locate_handle_buffer: *const c_void,
    pub locate_protocol: unsafe extern "efiapi" fn(
        protocol: *const Guid,
        registration: *mut c_void,
        interface: *mut *mut c_void,
    ) -> Status,
    pub install_multiple_protocol_interfaces: *const c_void,
}

#[repr(C)]
pub struct GraphicsOutputProtocol {
    pub query_mode: *const c_void,
    pub set_mode: *const c_void,
    pub blt: *const c_void,
    pub mode: *mut GraphicsOutputProtocolMode,
}

#[repr(C)]
pub struct GraphicsOutputProtocolMode {
    pub max_mode: u32,
    pub mode: u32,
    pub info: *mut GraphicsOutputModeInformation,
    pub size_of_info: usize,
    pub frame_buffer_base: u64,
    pub frame_buffer_size: usize,
}

#[repr(C)]
pub struct GraphicsOutputModeInformation {
    pub version: u32,
    pub horizontal_resolution: u32,
    pub vertical_resolution: u32,
    pub pixel_format: u32, // 0 = RGBR, 1 = BGRR
    pub pixel_information: [u32; 4],
    pub pixels_per_scan_line: u32,
}
