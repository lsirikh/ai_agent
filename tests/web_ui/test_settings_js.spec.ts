/**
 * Settings JavaScript Logic Tests
 *
 * Phase 10.4.2: Dashboard Settings JavaScript 테스트
 * TDD: Red → Green → Refactor
 */
import { test, expect } from '@playwright/test';

test.describe('Settings JavaScript Logic', () => {
    test.beforeEach(async ({ page }) => {
        // Navigate to settings page/tab
        await page.goto('/');
        // Click settings tab if using tab-based navigation
        const settingsTab = page.locator('[data-tab="settings"]');
        if (await settingsTab.isVisible()) {
            await settingsTab.click();
        }
    });

    test('test_load_settings_options', async ({ page }) => {
        /**
         * 설정 옵션 로드 테스트
         * - /api/settings/options 엔드포인트 호출
         * - 드롭다운이 API 데이터로 채워져야 함
         */
        // Wait for settings options to load
        await page.waitForResponse(response =>
            response.url().includes('/api/settings/options') &&
            response.status() === 200
        );

        // TTS engine dropdown should have options
        const ttsOptions = page.locator('[data-testid="tts-engine-select"] option');
        await expect(ttsOptions).not.toHaveCount(0);

        // STT model dropdown should have options
        const sttOptions = page.locator('[data-testid="stt-model-select"] option');
        await expect(sttOptions).not.toHaveCount(0);

        // LLM model dropdown should have options
        const llmOptions = page.locator('[data-testid="llm-model-select"] option');
        await expect(llmOptions).not.toHaveCount(0);
    });

    test('test_save_settings', async ({ page }) => {
        /**
         * 설정 저장 테스트
         * - Save Settings 버튼 클릭
         * - /api/settings/apply 엔드포인트 호출
         */
        // Mock the API response
        await page.route('**/api/settings/apply', async route => {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    applied: { tts: true, stt: true, llm: true },
                    restart_required: [],
                    message: 'Settings applied successfully'
                })
            });
        });

        // Click save settings button
        const saveBtn = page.locator('#saveSettingsBtn');
        await saveBtn.click();

        // Should show success message (alert or notification)
        page.on('dialog', async dialog => {
            expect(dialog.message()).toContain('Settings saved');
            await dialog.accept();
        });
    });

    test('test_show_restart_button', async ({ page }) => {
        /**
         * 재시작 버튼 표시 테스트
         * - LLM 모델 변경 시 재시작 필요
         * - 재시작 버튼이 표시되어야 함
         */
        // Mock the API response with restart required
        await page.route('**/api/settings/apply', async route => {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    applied: { llm: true },
                    restart_required: ['llm'],
                    restart_commands: { llm: 'docker-compose restart llm' },
                    message: 'Settings applied. Restart required for: llm'
                })
            });
        });

        // Handle dialog
        page.on('dialog', async dialog => {
            await dialog.accept();
        });

        // Click save settings button
        const saveBtn = page.locator('#saveSettingsBtn');
        await saveBtn.click();

        // Restart button should become visible
        const restartBtn = page.locator('#restartServicesBtn');
        await expect(restartBtn).toBeVisible();
    });

    test('test_engine_change_updates_voices', async ({ page }) => {
        /**
         * 엔진 변경 시 음성 목록 업데이트 테스트
         * - TTS 엔진 변경 시 정보 텍스트가 업데이트되어야 함
         */
        const ttsSelect = page.locator('[data-testid="tts-engine-select"]');
        const ttsInfo = page.locator('#ttsEngineInfo');

        // Change to edge_tts
        await ttsSelect.selectOption('edge_tts');

        // Info text should update
        await expect(ttsInfo).toContainText(/Cloud|Internet/i);

        // Change to melo
        await ttsSelect.selectOption('melo');

        // Info text should update
        await expect(ttsInfo).toContainText(/Korean|GPU/i);
    });
});
