package xiaozhi.modules.config.service.impl;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import xiaozhi.common.redis.RedisKeys;
import xiaozhi.common.redis.RedisUtils;
import xiaozhi.modules.agent.dao.AgentVoicePrintDao;
import xiaozhi.modules.agent.service.AgentContextProviderService;
import xiaozhi.modules.agent.service.AgentMcpAccessPointService;
import xiaozhi.modules.agent.service.AgentPluginMappingService;
import xiaozhi.modules.agent.service.AgentService;
import xiaozhi.modules.agent.service.AgentTemplateService;
import xiaozhi.modules.correctword.service.CorrectWordFileService;
import xiaozhi.modules.device.service.DeviceService;
import xiaozhi.modules.model.service.ModelConfigService;
import xiaozhi.modules.sys.dto.SysParamsDTO;
import xiaozhi.modules.sys.service.SysParamsService;
import xiaozhi.modules.timbre.service.TimbreService;
import xiaozhi.modules.voiceclone.service.VoiceCloneService;

class ConfigServiceImplTest {

    @Test
    void cachedServerConfigIsCheckedAsAStringKeyedMapWithoutChangingNestedValues() {
        RedisUtils redisUtils = mock(RedisUtils.class);
        Map<String, Object> nested = new HashMap<>();
        nested.put("enabled", true);
        Map<String, Object> cached = new HashMap<>();
        cached.put("features", nested);
        when(redisUtils.get(RedisKeys.getServerConfigKey())).thenReturn(cached);

        ConfigServiceImpl service = newService(mock(SysParamsService.class), redisUtils);

        Map<String, Object> result = service.getConfig(true);

        assertNotSame(cached, result);
        assertSame(nested, result.get("features"));
        assertEquals(true, ((Map<?, ?>) result.get("features")).get("enabled"));
    }

    @Test
    void nestedSystemParametersStillShareAndPopulateTheSameConfigBranch() {
        SysParamsService sysParamsService = mock(SysParamsService.class);
        SysParamsDTO enabled = parameter("server.features.enabled", "true", "boolean");
        SysParamsDTO labels = parameter("server.features.labels", "first;second", "array");
        when(sysParamsService.list(anyMap())).thenReturn(List.of(enabled, labels));
        ConfigServiceImpl service = newService(sysParamsService, mock(RedisUtils.class));
        Map<String, Object> config = new HashMap<>();

        Object returned = ReflectionTestUtils.invokeMethod(service, "buildConfig", config);

        assertSame(config, returned);
        Map<?, ?> server = assertInstanceOf(Map.class, config.get("server"));
        Map<?, ?> features = assertInstanceOf(Map.class, server.get("features"));
        assertEquals(true, features.get("enabled"));
        assertEquals(List.of("first", "second"), features.get("labels"));
    }


    @Test
    void modeSelectsOnlyTheActiveInputPipelineAndPreservesSavedSelections() {
        var models = mock(ModelConfigService.class);
        var agents = mock(AgentService.class);
        var devices = mock(DeviceService.class);
        var agent = new xiaozhi.modules.agent.vo.AgentInfoVO();
        agent.setId("a");
        agent.setAgentName("test");
        agent.setAsrModelId("asr");
        agent.setLlmModelId("llm");
        agent.setVllmModelId("vision");
        agent.setIntentModelId("Intent_nointent");
        agent.setOmniModelId("omni");
        agent.setSystemPrompt("Original prompt");
        var device = new xiaozhi.modules.device.entity.DeviceEntity();
        device.setAgentId("a");
        when(devices.getDeviceByMacAddress("mac")).thenReturn(device);
        when(agents.getAgentById("a")).thenReturn(agent);
        for (String id : List.of("asr", "llm", "vision", "Intent_nointent", "omni")) {
            var model = new xiaozhi.modules.model.entity.ModelConfigEntity();
            model.setId(id);
            model.setIsEnabled(1);
            model.setModelType("omni".equals(id) ? "OMNI" : "LLM");
            model.setConfigJson(new cn.hutool.json.JSONObject().set("type", "omni".equals(id) ? "qwen_omni" : "openai"));
            when(models.selectById(id)).thenReturn(model);
            when(models.getModelByIdFromCache(id)).thenReturn(model);
        }
        var service = newService(mock(SysParamsService.class), mock(RedisUtils.class));
        ReflectionTestUtils.setField(service, "modelConfigService", models);
        ReflectionTestUtils.setField(service, "agentService", agents);
        ReflectionTestUtils.setField(service, "deviceService", devices);
        var original = service.getAgentModels("mac", Map.of());
        agent.setModelMode("separate");
        assertEquals(original, service.getAgentModels("mac", Map.of()));
        org.junit.jupiter.api.Assertions.assertFalse(original.containsKey("OMNI"));
        org.junit.jupiter.api.Assertions.assertFalse(original.containsKey("model_mode"));
        agent.setModelMode("omni");
        var unified = service.getAgentModels("mac", Map.of());
        assertEquals("omni", unified.get("model_mode"));
        var selected = (Map<?, ?>) unified.get("selected_module");
        assertEquals("omni", selected.get("OMNI"));
        for (String type : List.of("ASR", "LLM", "VLLM")) {
            org.junit.jupiter.api.Assertions.assertFalse(selected.containsKey(type));
        }
        assertEquals("Original prompt", unified.get("prompt"));
        assertEquals("asr", agent.getAsrModelId());
        assertEquals("llm", agent.getLlmModelId());
        assertEquals("vision", agent.getVllmModelId());
        agent.setModelMode("separate");
        assertEquals(original, service.getAgentModels("mac", Map.of()));
    }

    private static SysParamsDTO parameter(String code, String value, String type) {
        SysParamsDTO parameter = new SysParamsDTO();
        parameter.setParamCode(code);
        parameter.setParamValue(value);
        parameter.setValueType(type);
        return parameter;
    }

    private static ConfigServiceImpl newService(SysParamsService sysParamsService, RedisUtils redisUtils) {
        return new ConfigServiceImpl(
                sysParamsService,
                mock(DeviceService.class),
                mock(ModelConfigService.class),
                mock(AgentService.class),
                mock(AgentTemplateService.class),
                redisUtils,
                mock(TimbreService.class),
                mock(AgentPluginMappingService.class),
                mock(AgentMcpAccessPointService.class),
                mock(AgentContextProviderService.class),
                mock(VoiceCloneService.class),
                mock(AgentVoicePrintDao.class),
                mock(CorrectWordFileService.class));
    }
}
