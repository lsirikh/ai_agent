/**
 * Settings UI Enhancement Tests
 *
 * Phase 10.4: Dashboard Settings UI - Dynamic Model Selection
 * TDD: Red → Green → Refactor
 */
import { test, expect } from '@playwright/test';

test.describe('Settings Tab UI Enhancement', () => {
    test.beforeEach(async ({ page }) => {
        // Navigate to settings page/tab
        await page.goto('/');
        // Click settings tab if using tab-based navigation
        const settingsTab = page.locator('[data-tab="settings"]');
        if (await settingsTab.isVisible()) {
            await settingsTab.click();
        }
    });

    test('test_settings_tab_renders', async ({ page }) => {
        /**
         * Settings 탭이 렌더링되는지 확인
         * - Settings 탭이 존재해야 함
         * - 탭 클릭 시 Settings 콘텐츠가 표시되어야 함
         */
        // Settings tab should be visible
        const settingsTab = page.locator('[data-tab="settings"]');
        await expect(settingsTab).toBeVisible();

        // Settings content should be displayed after clicking
        const settingsContent = page.locator('#settings');
        await expect(settingsContent).toHaveClass(/active/);

        // Should have Settings title
        await expect(settingsContent.locator('.card-title')).toContainText('Settings');
    });

    test('test_gpu_memory_indicator', async ({ page }) => {
        /**
         * GPU 메모리 인디케이터가 표시되는지 확인
         * - GPU 메모리 사용량 표시 영역이 있어야 함
         * - 현재 VRAM 사용량이 표시되어야 함
         */
        const settingsContent = page.locator('#settings');

        // GPU memory indicator should exist
        const gpuIndicator = settingsContent.locator('[data-testid="gpu-memory-indicator"]');
        await expect(gpuIndicator).toBeVisible();

        // Should show VRAM info
        await expect(gpuIndicator).toContainText(/VRAM|GPU|Memory/i);
    });

    test('test_tts_engine_dropdown', async ({ page }) => {
        /**
         * TTS 엔진 드롭다운이 동작하는지 확인
         * - TTS 엔진 선택 드롭다운이 있어야 함
         * - MeloTTS, Kokoro, Edge-TTS, gTTS 옵션이 있어야 함
         */
        const settingsContent = page.locator('#settings');

        // TTS engine dropdown should exist
        const ttsEngineSelect = settingsContent.locator('[data-testid="tts-engine-select"]');
        await expect(ttsEngineSelect).toBeVisible();

        // Should have engine options
        await expect(ttsEngineSelect.locator('option[value="melo"]')).toBeAttached();
        await expect(ttsEngineSelect.locator('option[value="kokoro"]')).toBeAttached();
        await expect(ttsEngineSelect.locator('option[value="edge_tts"]')).toBeAttached();
        await expect(ttsEngineSelect.locator('option[value="gtts"]')).toBeAttached();
    });

    test('test_stt_model_dropdown', async ({ page }) => {
        /**
         * STT 모델 드롭다운이 동작하는지 확인
         * - STT 모델 선택 드롭다운이 있어야 함
         * - Whisper 모델 옵션들이 있어야 함
         */
        const settingsContent = page.locator('#settings');

        // STT model dropdown should exist
        const sttModelSelect = settingsContent.locator('[data-testid="stt-model-select"]');
        await expect(sttModelSelect).toBeVisible();

        // Should have model options
        await expect(sttModelSelect.locator('option[value="tiny"]')).toBeAttached();
        await expect(sttModelSelect.locator('option[value="small"]')).toBeAttached();
        await expect(sttModelSelect.locator('option[value="medium"]')).toBeAttached();
        await expect(sttModelSelect.locator('option[value="large-v3"]')).toBeAttached();
    });

    test('test_llm_model_dropdown', async ({ page }) => {
        /**
         * LLM 모델 드롭다운이 동작하는지 확인
         * - LLM 모델 선택 드롭다운이 있어야 함
         * - 다양한 LLM 모델 옵션들이 있어야 함
         */
        const settingsContent = page.locator('#settings');

        // LLM model dropdown should exist
        const llmModelSelect = settingsContent.locator('[data-testid="llm-model-select"]');
        await expect(llmModelSelect).toBeVisible();

        // Should have LLM model options (at least one)
        const options = llmModelSelect.locator('option');
        await expect(options).not.toHaveCount(0);
    });
});
