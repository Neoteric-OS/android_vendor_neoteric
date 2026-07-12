# Setup SOONG_CONFIG_* vars to export the vars listed above.
# Documentation here:
# https://github.com/LineageOS/android_build_soong/commit/8328367c44085b948c003116c0ed74a047237a69

# PA Variables

PATH_OVERRIDE_SOONG := $(shell echo $(TOOLS_PATH_OVERRIDE))

# Add variables that we wish to make available to soong here.
EXPORT_TO_SOONG := \
    KERNEL_ARCH \
    KERNEL_BUILD_OUT_PREFIX \
    KERNEL_CROSS_COMPILE \
    KERNEL_MAKE_CMD \
    KERNEL_MAKE_FLAGS \
    KERNEL_PATH \
    PATH_OVERRIDE_SOONG \
    TARGET_KERNEL_CONFIG \
    TARGET_KERNEL_SOURCE \
    TARGET_KERNEL_PLATFORM_TARGET \
    TARGET_MAX_PAGE_SIZE_SUPPORTED \
    TARGET_PREBUILT_KERNEL_HEADERS

SOONG_CONFIG_NAMESPACES += neotericVarsPlugin

SOONG_CONFIG_neotericVarsPlugin :=

define addVar
  SOONG_CONFIG_neotericVarsPlugin += $(1)
  SOONG_CONFIG_neotericVarsPlugin_$(1) := $($1)
endef

$(foreach v,$(EXPORT_TO_SOONG),$(eval $(call addVar,$(v))))

SOONG_CONFIG_NAMESPACES += neotericGlobalVars
SOONG_CONFIG_neotericGlobalVars += \
    aapt_version_code \
    needs_camera_boottime \
    powershare_node \
    target_camera_package_name \
    target_health_charging_control_charging_enabled \
    target_health_charging_control_charging_disabled \
    target_health_charging_control_deadline_path \
    target_health_charging_control_supports_bypass \
    target_health_charging_control_supports_deadline \
    target_health_charging_control_supports_toggle \
    target_init_vendor_lib \
    target_ld_shim_libs \
    target_libcameraservice_ext_lib \
    target_process_sdk_version_override \
    target_surfaceflinger_udfps_lib

ifneq ($(TARGET_HEALTH_CHARGING_CONTROL_CHARGING_PATH),)
SOONG_CONFIG_neotericGlobalVars += \
    target_health_charging_control_charging_path
endif

# Set default values
TARGET_HEALTH_CHARGING_CONTROL_CHARGING_ENABLED ?= 1
TARGET_HEALTH_CHARGING_CONTROL_CHARGING_DISABLED ?= 0
TARGET_HEALTH_CHARGING_CONTROL_SUPPORTS_BYPASS ?= true
TARGET_HEALTH_CHARGING_CONTROL_SUPPORTS_DEADLINE ?= false
TARGET_HEALTH_CHARGING_CONTROL_SUPPORTS_TOGGLE ?= true
TARGET_INIT_VENDOR_LIB ?= vendor_init
TARGET_SURFACEFLINGER_UDFPS_LIB ?= surfaceflinger_udfps_lib
TARGET_CAMERA_SERVICE_EXT_LIB ?= libcameraservice_ext_lib

# Soong value variables
SOONG_CONFIG_neotericGlobalVars_aapt_version_code := $(shell date -u +%Y%m%d)
SOONG_CONFIG_neotericGlobalVars_needs_camera_boottime := $(TARGET_CAMERA_BOOTTIME_TIMESTAMP)
SOONG_CONFIG_neotericGlobalVars_powershare_node := $(TARGET_POWERSHARE_NODE)
SOONG_CONFIG_neotericGlobalVars_target_camera_package_name := $(TARGET_CAMERA_PACKAGE_NAME)
SOONG_CONFIG_neotericGlobalVars_target_init_vendor_lib := $(TARGET_INIT_VENDOR_LIB)
SOONG_CONFIG_neotericGlobalVars_target_ld_shim_libs := $(subst $(space),:,$(TARGET_LD_SHIM_LIBS))
SOONG_CONFIG_neotericGlobalVars_target_process_sdk_version_override := $(TARGET_PROCESS_SDK_VERSION_OVERRIDE)
SOONG_CONFIG_neotericGlobalVars_target_surfaceflinger_udfps_lib := $(TARGET_SURFACEFLINGER_UDFPS_LIB)
ifneq ($(TARGET_HEALTH_CHARGING_CONTROL_CHARGING_PATH),)
SOONG_CONFIG_neotericGlobalVars_target_health_charging_control_charging_path := $(TARGET_HEALTH_CHARGING_CONTROL_CHARGING_PATH)
endif
SOONG_CONFIG_neotericGlobalVars_target_health_charging_control_charging_enabled := $(TARGET_HEALTH_CHARGING_CONTROL_CHARGING_ENABLED)
SOONG_CONFIG_neotericGlobalVars_target_health_charging_control_charging_disabled := $(TARGET_HEALTH_CHARGING_CONTROL_CHARGING_DISABLED)
SOONG_CONFIG_neotericGlobalVars_target_health_charging_control_deadline_path := $(TARGET_HEALTH_CHARGING_CONTROL_DEADLINE_PATH)
SOONG_CONFIG_neotericGlobalVars_target_health_charging_control_supports_bypass := $(TARGET_HEALTH_CHARGING_CONTROL_SUPPORTS_BYPASS)
SOONG_CONFIG_neotericGlobalVars_target_health_charging_control_supports_deadline := $(TARGET_HEALTH_CHARGING_CONTROL_SUPPORTS_DEADLINE)
SOONG_CONFIG_neotericGlobalVars_target_health_charging_control_supports_toggle := $(TARGET_HEALTH_CHARGING_CONTROL_SUPPORTS_TOGGLE)
SOONG_CONFIG_neotericGlobalVars_target_libcameraservice_ext_lib := $(TARGET_CAMERA_SERVICE_EXT_LIB)

# Qualcomm variables
SOONG_CONFIG_NAMESPACES += aosp_vs_qva
SOONG_CONFIG_aosp_vs_qva += aosp_or_qva
SOONG_CONFIG_aosp_vs_qva_aosp_or_qva := qva
