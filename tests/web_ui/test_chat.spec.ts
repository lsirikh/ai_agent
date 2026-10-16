/**
 * Chat Page Tests
 *
 * Phase 9.6: Web Dashboard - Chat 페이지 테스트
 */
import { test, expect } from '@playwright/test';

test.describe('Chat Page', () => {
    test.beforeEach(async ({ page }) => {
        await page.goto('/chat');
    });

    test('should render chat page', async ({ page }) => {
        // Chat 페이지가 렌더링되어야 한다
        await expect(page.locator('h1')).toContainText('Chat');
    });

    test('should display message input area', async ({ page }) => {
        // 메시지 입력 영역이 표시되어야 한다
        const chatInput = page.locator('[data-testid="chat-input"]');
        await expect(chatInput).toBeVisible();

        const inputField = page.locator('[data-testid="message-input"]');
        await expect(inputField).toBeVisible();

        const sendButton = page.locator('[data-testid="send-button"]');
        await expect(sendButton).toBeVisible();
    });

    test('should display message list area', async ({ page }) => {
        // 메시지 목록 영역이 표시되어야 한다
        const messageList = page.locator('[data-testid="message-list"]');
        await expect(messageList).toBeVisible();
    });

    test('should display RAG toggle', async ({ page }) => {
        // RAG 토글 스위치가 표시되어야 한다
        const ragToggle = page.locator('[data-testid="rag-toggle"]');
        await expect(ragToggle).toBeVisible();
    });

    test('should allow typing in message input', async ({ page }) => {
        // 메시지 입력이 가능해야 한다
        const inputField = page.locator('[data-testid="message-input"]');
        await inputField.fill('안녕하세요');
        await expect(inputField).toHaveValue('안녕하세요');
    });

    test('should toggle RAG setting', async ({ page }) => {
        // RAG 토글이 동작해야 한다
        const ragToggle = page.locator('[data-testid="rag-toggle"]');
        const checkbox = ragToggle.locator('input[type="checkbox"]');

        // 기본값은 체크됨 (RAG 활성화)
        await expect(checkbox).toBeChecked();

        // 토글 클릭
        await checkbox.click();
        await expect(checkbox).not.toBeChecked();

        // 다시 토글
        await checkbox.click();
        await expect(checkbox).toBeChecked();
    });

    test('should send message on button click', async ({ page }) => {
        // 버튼 클릭으로 메시지 전송이 가능해야 한다
        const inputField = page.locator('[data-testid="message-input"]');
        const sendButton = page.locator('[data-testid="send-button"]');

        await inputField.fill('테스트 메시지');
        await sendButton.click();

        // 메시지가 목록에 추가되어야 함
        const messageList = page.locator('[data-testid="message-list"]');
        await expect(messageList.locator('text=테스트 메시지')).toBeVisible();
    });

    test('should send message on enter key', async ({ page }) => {
        // Enter 키로 메시지 전송이 가능해야 한다
        const inputField = page.locator('[data-testid="message-input"]');

        await inputField.fill('엔터 테스트');
        await inputField.press('Enter');

        // 메시지가 목록에 추가되어야 함
        const messageList = page.locator('[data-testid="message-list"]');
        await expect(messageList.locator('text=엔터 테스트')).toBeVisible();
    });

    test('should clear input after sending', async ({ page }) => {
        // 전송 후 입력 필드가 비워져야 한다
        const inputField = page.locator('[data-testid="message-input"]');
        const sendButton = page.locator('[data-testid="send-button"]');

        await inputField.fill('전송 테스트');
        await sendButton.click();

        // 입력 필드가 비워져야 함
        await expect(inputField).toHaveValue('');
    });

    test('should display assistant response', async ({ page }) => {
        // AI 응답이 표시되어야 한다
        const inputField = page.locator('[data-testid="message-input"]');
        const sendButton = page.locator('[data-testid="send-button"]');

        await inputField.fill('안녕');
        await sendButton.click();

        // AI 응답 대기
        const messageList = page.locator('[data-testid="message-list"]');
        const assistantMessage = messageList.locator('[data-testid="assistant-message"]');

        // 응답이 나타날 때까지 대기
        await expect(assistantMessage.first()).toBeVisible({ timeout: 10000 });
    });

    test('should show new chat button', async ({ page }) => {
        // 새 채팅 버튼이 표시되어야 한다
        const newChatButton = page.locator('[data-testid="new-chat-button"]');
        await expect(newChatButton).toBeVisible();
    });

    test('should have navigation to chat page', async ({ page }) => {
        // 네비게이션 메뉴에 Chat 링크가 있어야 한다
        await page.goto('/');
        const nav = page.locator('nav');
        await expect(nav.locator('text=Chat')).toBeVisible();

        // Chat 페이지로 이동
        await page.click('nav >> text=Chat');
        await expect(page).toHaveURL(/.*chat/);
    });
});
