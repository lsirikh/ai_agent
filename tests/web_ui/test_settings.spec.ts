/**
 * Settings Page Tests
 *
 * Phase 5.7: Web Dashboard - Settings 페이지 테스트
 */
import { test, expect } from '@playwright/test';

test.describe('Settings Page', () => {
    test.beforeEach(async ({ page }) => {
        await page.goto('/settings');
    });

    test('should render settings page', async ({ page }) => {
        // Settings 페이지가 렌더링되어야 한다
        await expect(page.locator('h1')).toContainText('Settings');
    });

    test('should display LLM settings section', async ({ page }) => {
        // LLM 설정 섹션이 표시되어야 한다
        const llmSection = page.locator('[data-testid="llm-settings"]');
        await expect(llmSection).toBeVisible();
        await expect(llmSection.locator('text=LLM Settings')).toBeVisible();

        // 각 설정 필드 확인
        await expect(llmSection.locator('input[name="model"]')).toBeVisible();
        await expect(llmSection.locator('input[name="temperature"]')).toBeVisible();
        await expect(llmSection.locator('input[name="max_tokens"]')).toBeVisible();
        await expect(llmSection.locator('textarea[name="system_prompt"]')).toBeVisible();
    });

    test('should display TTS settings section', async ({ page }) => {
        // TTS 설정 섹션이 표시되어야 한다
        const ttsSection = page.locator('[data-testid="tts-settings"]');
        await expect(ttsSection).toBeVisible();
        await expect(ttsSection.locator('text=TTS Settings')).toBeVisible();

        // 각 설정 필드 확인
        await expect(ttsSection.locator('select[name="voice"]')).toBeVisible();
        await expect(ttsSection.locator('input[name="speed"]')).toBeVisible();
    });

    test('should display STT settings section', async ({ page }) => {
        // STT 설정 섹션이 표시되어야 한다
        const sttSection = page.locator('[data-testid="stt-settings"]');
        await expect(sttSection).toBeVisible();
        await expect(sttSection.locator('text=STT Settings')).toBeVisible();

        // 각 설정 필드 확인
        await expect(sttSection.locator('select[name="language"]')).toBeVisible();
        await expect(sttSection.locator('input[name="beam_size"]')).toBeVisible();
    });

    test('should display audio settings section', async ({ page }) => {
        // Audio 설정 섹션이 표시되어야 한다
        const audioSection = page.locator('[data-testid="audio-settings"]');
        await expect(audioSection).toBeVisible();
        await expect(audioSection.locator('text=Audio Settings')).toBeVisible();

        // 각 설정 필드 확인
        await expect(audioSection.locator('input[name="vad_threshold"]')).toBeVisible();
        await expect(audioSection.locator('input[name="silence_duration"]')).toBeVisible();
    });

    test('should update LLM temperature setting', async ({ page }) => {
        // LLM temperature 설정을 업데이트할 수 있어야 한다
        const temperatureInput = page.locator('[data-testid="llm-settings"] input[name="temperature"]');

        await temperatureInput.fill('0.8');
        await page.click('[data-testid="llm-settings"] button[type="submit"]');

        // 성공 메시지 확인
        await expect(page.locator('text=Settings saved')).toBeVisible();
    });

    test('should update TTS voice setting', async ({ page }) => {
        // TTS voice 설정을 업데이트할 수 있어야 한다
        const voiceSelect = page.locator('[data-testid="tts-settings"] select[name="voice"]');

        await voiceSelect.selectOption('af_bella');
        await page.click('[data-testid="tts-settings"] button[type="submit"]');

        // 성공 메시지 확인
        await expect(page.locator('text=Settings saved')).toBeVisible();
    });

    test('should validate temperature range', async ({ page }) => {
        // temperature 값 범위를 검증해야 한다 (0.0 ~ 2.0)
        const temperatureInput = page.locator('[data-testid="llm-settings"] input[name="temperature"]');

        // 유효하지 않은 값 입력
        await temperatureInput.fill('3.0');
        await page.click('[data-testid="llm-settings"] button[type="submit"]');

        // 에러 메시지 확인
        await expect(page.locator('text=Temperature must be between 0 and 2')).toBeVisible();
    });

    test('should validate max_tokens range', async ({ page }) => {
        // max_tokens 값 범위를 검증해야 한다
        const maxTokensInput = page.locator('[data-testid="llm-settings"] input[name="max_tokens"]');

        // 유효하지 않은 값 입력
        await maxTokensInput.fill('10000');
        await page.click('[data-testid="llm-settings"] button[type="submit"]');

        // 에러 메시지 확인
        await expect(page.locator('text=Max tokens must be between 1 and 8192')).toBeVisible();
    });

    test('should reset settings to default', async ({ page }) => {
        // 설정을 기본값으로 초기화할 수 있어야 한다
        await page.click('button[data-testid="reset-defaults"]');

        // 확인 다이얼로그
        await page.click('button:has-text("Confirm")');

        // 성공 메시지 확인
        await expect(page.locator('text=Settings reset to defaults')).toBeVisible();
    });

    test('should load current settings on page load', async ({ page }) => {
        // 페이지 로드 시 현재 설정을 불러와야 한다
        const temperatureInput = page.locator('[data-testid="llm-settings"] input[name="temperature"]');

        // 값이 로드되었는지 확인 (빈 값이 아님)
        await expect(temperatureInput).not.toHaveValue('');
    });
});
