package xiaozhi.modules.agent.service.impl;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import cn.hutool.json.JSONObject;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.test.util.ReflectionTestUtils;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.utils.MessageUtils;
import xiaozhi.modules.agent.entity.AgentEntity;
import xiaozhi.modules.model.entity.ModelConfigEntity;
import xiaozhi.modules.model.service.ModelConfigService;

class OmniIntentValidationTest {
    @ParameterizedTest
    @ValueSource(strings = {"qwen_omni", "openai", "ollama", "dify"})
    void savingAndRestoringAgreeOnFunctionCallingSupport(String type) {
        ModelConfigService models = mock(ModelConfigService.class);
        ModelConfigEntity model = new ModelConfigEntity();
        model.setConfigJson(new JSONObject().set("type", type));
        when(models.selectById("chosen")).thenReturn(model);

        AgentServiceImpl save = mock(AgentServiceImpl.class, CALLS_REAL_METHODS);
        AgentSnapshotServiceImpl restore = mock(AgentSnapshotServiceImpl.class, CALLS_REAL_METHODS);
        ReflectionTestUtils.setField(save, "modelConfigService", models);
        ReflectionTestUtils.setField(restore, "modelConfigService", models);
        AgentEntity agent = new AgentEntity();
        agent.setLlmModelId("chosen");
        agent.setIntentModelId("Intent_function_call");

        boolean supported = "openai".equals(type) || "ollama".equals(type);
        Boolean valid = ReflectionTestUtils.invokeMethod(save, "validateLLMIntentParams",
                "chosen", "Intent_function_call");
        assertEquals(supported, valid);
        if (supported) {
            assertDoesNotThrow(() -> ReflectionTestUtils.invokeMethod(restore, "validateRestoreParams", agent));
        } else {
            try (var messages = mockStatic(MessageUtils.class)) {
                RenException error = assertThrows(RenException.class,
                        () -> ReflectionTestUtils.invokeMethod(restore, "validateRestoreParams", agent));
                assertEquals(ErrorCode.LLM_INTENT_PARAMS_MISMATCH, error.getCode());
            }
        }
        // Independent intent selection remains available for every provider.
        assertEquals(Boolean.TRUE, ReflectionTestUtils.invokeMethod(save,
                "validateLLMIntentParams", "chosen", "Intent_intent_llm"));
    }

    @org.junit.jupiter.api.Test
    void omniModeValidatesIndependentModelAndPreservesLegacyChoices() {
        ModelConfigService models = mock(ModelConfigService.class);
        ModelConfigEntity omni = new ModelConfigEntity();
        omni.setModelType("OMNI");
        omni.setIsEnabled(1);
        omni.setConfigJson(new JSONObject().set("type", "qwen_omni"));
        when(models.selectById("omni")).thenReturn(omni);
        AgentSnapshotServiceImpl restore = mock(AgentSnapshotServiceImpl.class, CALLS_REAL_METHODS);
        ReflectionTestUtils.setField(restore, "modelConfigService", models);
        AgentEntity agent = new AgentEntity();
        agent.setModelMode("omni");
        agent.setOmniModelId("omni");
        agent.setLlmModelId("old-llm");
        agent.setAsrModelId("old-asr");
        agent.setVllmModelId("old-vision");
        agent.setIntentModelId("Intent_function_call");
        assertDoesNotThrow(() -> ReflectionTestUtils.invokeMethod(restore, "validateRestoreParams", agent));
        verify(models, never()).selectById("old-llm");
        assertEquals("old-llm", agent.getLlmModelId());
        assertEquals("old-asr", agent.getAsrModelId());
        assertEquals("old-vision", agent.getVllmModelId());
        omni.setIsEnabled(0);
        assertThrows(RenException.class, () -> ReflectionTestUtils.invokeMethod(restore, "validateRestoreParams", agent));
        omni.setIsEnabled(1);
        omni.setModelType("LLM");
        assertThrows(RenException.class, () -> ReflectionTestUtils.invokeMethod(restore, "validateRestoreParams", agent));
    }
}
