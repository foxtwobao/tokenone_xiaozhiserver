package xiaozhi.modules.agent.util;

import xiaozhi.common.exception.RenException;
import xiaozhi.modules.model.entity.ModelConfigEntity;
import xiaozhi.modules.model.service.ModelConfigService;

/** Validates only the opt-in branch. Existing separate-mode validation stays intact. */
public final class OmniModelValidation {
    private OmniModelValidation() {}

    public static void validate(String mode, String id, ModelConfigService models) {
        if (mode == null || "separate".equals(mode)) return;
        if (!"omni".equals(mode)) throw new RenException("输入模型模式必须为 separate 或 omni");
        ModelConfigEntity model = id == null || id.isBlank() ? null : models.selectById(id);
        if (model == null || !"OMNI".equalsIgnoreCase(model.getModelType())
                || !Integer.valueOf(1).equals(model.getIsEnabled())
                || model.getConfigJson() == null
                || !"qwen_omni".equals(model.getConfigJson().get("type"))) {
            throw new RenException("请选择已启用的 Omni 多模态模型");
        }
    }
}
