import { test, expect } from '@playwright/test';
import { registerAndLogin, loginViaUI } from './fixtures';

test.describe('Auth', () => {
  test('a registered user can log in through the UI and reach the dashboard', async ({ page, request }) => {
    const user = await registerAndLogin(request);
    await loginViaUI(page, user.email, user.password);
    await expect(page).toHaveURL(/\/dashboard/);
  });

  test('an invalid login shows an error and stays on the login page', async ({ page }) => {
    await page.goto('/login');
    await page.getByPlaceholder('Email').fill('nobody@example.com');
    await page.getByPlaceholder('Password').fill('wrongpassword');
    await page.getByRole('button', { name: 'Log in' }).click();
    await expect(page.getByText(/incorrect|invalid|not authenticated/i)).toBeVisible({ timeout: 10000 });
    await expect(page).toHaveURL(/\/login/);
  });
});
