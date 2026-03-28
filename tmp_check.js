    <script>
        // 強制的にService Workerを解除する（キャッシュトラップ脱出のため）
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.getRegistrations().then(function(registrations) {
                for(let registration of registrations) {
                    registration.unregister();
                }
            });
        }
    </script>
    <script>
        if (!RyubeeAPI.requireAuth()) throw new Error("Not authenticated");

        let allCustomers = [];
        let editingId = null;

        document.addEventListener('DOMContentLoaded', loadCustomers);

        async function loadCustomers() {
            try {
                allCustomers = await RyubeeAPI.fetchCustomers();
                filterCustomers();
            } catch (e) {
                document.getElementById('customerList').innerHTML = `<div class="alert alert-danger">${e.message}</div>`;
            }
        }

        function filterCustomers() {
            const q = document.getElementById('searchInput').value.toLowerCase();
            const filtered = allCustomers.filter(c => {
                const text = (c.name + c.address + c.phone + c.contact_person + c.email).toLowerCase();
                return text.includes(q);
            });
            renderCustomers(filtered);
        }

        function renderCustomers(customers) {
            const list = document.getElementById('customerList');
            if (!customers.length) {
                list.innerHTML = '<p style="text-align:center;color:var(--text-tertiary);margin-top:30px;">顧客が見つかりません</p>';
                return;
            }
            list.innerHTML = customers.map(c => {
                const typeBadge = c.contract_type === 'subscription'
                    ? '<span class="badge badge-success">定期契約</span>'
                    : '<span class="badge badge-primary">スポット</span>';
                const expiry = c.contract_expiry_date
                    ? `<div class="cc-expiry">📋 契約期限: ${c.contract_expiry_date}</div>` : '';
                return `
                    <div class="customer-card" onclick="openEdit('${c.id}')">
                        <div class="cc-top">
                            <span class="cc-name">${utils.escapeHtml(c.name)}</span>
                            ${typeBadge}
                        </div>
                        ${c.contact_person ? `<div class="cc-meta">👤 ${utils.escapeHtml(c.contact_person)}</div>` : ''}
                        <div class="cc-meta">📍 ${utils.escapeHtml(c.address || '未設定')}</div>
                        <div class="cc-meta">📞 ${utils.escapeHtml(c.phone || '未設定')}</div>
                        ${c.email ? `<div class="cc-meta">✉️ ${utils.escapeHtml(c.email)}</div>` : ''}
                        ${expiry}
                    </div>
                `;
            }).join('');
        }

        function openModal(cust = null) {
            editingId = cust ? cust.id : null;
            document.getElementById('modalTitle').textContent = cust ? '顧客を編集' : '顧客を登録';
            document.getElementById('saveBtn').textContent = cust ? '更新する' : '登録する';
            document.getElementById('deleteBtn').style.display = cust ? 'block' : 'none';
            const printBtn = document.getElementById('printContractBtn');
            if (cust) {
                printBtn.style.display = 'block';
                printBtn.href = `contract-form.html?id=${cust.id}`;
            } else {
                printBtn.style.display = 'none';
            }
            document.getElementById('custName').value = cust?.name || '';
            document.getElementById('custContact').value = cust?.contact_person || '';
            document.getElementById('custAddress').value = cust?.address || '';
            document.getElementById('custPhone').value = cust?.phone || '';
            document.getElementById('custEmail').value = cust?.email || '';
            document.getElementById('custType').value = cust?.contract_type || 'spot';
            document.getElementById('custExpiry').value = cust?.contract_expiry_date || '';
            document.getElementById('custClosingDay').value = cust?.billing_closing_day || '31';
            document.getElementById('custPayMonthOffset').value = cust?.payment_due_month_offset ?? '1';
            document.getElementById('custPayDay').value = cust?.payment_due_day || '31';
            document.getElementById('custNotes').value = cust?.notes || '';

            // 拡張データ(JSON)の展開
            let fd = {};
            if (cust && cust.form_data) {
                try { fd = JSON.parse(cust.form_data); } catch (e) { }
            }
            document.getElementById('custMobile').value = fd.mobile || '';
            document.getElementById('custBranchName').value = fd.branch_name || '';
            document.getElementById('custBranchAddress').value = fd.branch_address || '';
            document.getElementById('custIndustryType').value = fd.industry_type || '';
            document.getElementById('custAvgVolume').value = fd.average_volume || '';
            document.getElementById('custFreqGeneral').value = fd.collection_general || '';
            document.getElementById('custFreqRecycle').value = fd.collection_recycle || '';
            document.getElementById('custFreqPlastic').value = fd.collection_plastic || '';
            document.getElementById('custFreqPaper').value = fd.collection_paper || '';
            document.getElementById('custBusinessHours').value = fd.business_hours || '';
            document.getElementById('custHoliday').value = fd.regular_holiday || '';
            document.getElementById('custStartDate').value = fd.collection_start_date || '';
            document.getElementById('custPaymentMethod').value = fd.payment_method || '振込';
            document.getElementById('custBillingAddress').value = fd.billing_address || '';
            document.getElementById('custBillingEmail').value = fd.billing_email || '';
            document.getElementById('custBillingContact').value = fd.billing_contact || '';

            // 単価リストの展開
            document.getElementById('pricingListContainer').innerHTML = '';
            if (fd.pricing_list && Array.isArray(fd.pricing_list) && fd.pricing_list.length > 0) {
                fd.pricing_list.forEach(p => addPricingRow(p.item, p.price, p.unit));
            } else {
                if (!cust) addPricingRow('', '', 'kg');
            }

            document.getElementById('custOverlay').classList.add('show');
        }

        function addPricingRow(item = '', price = '', unit = 'kg') {
            const container = document.getElementById('pricingListContainer');
            const row = document.createElement('div');
            row.className = 'pricing-row';
            row.innerHTML = `
                <input type="text" class="pr-item" placeholder="品名(例: 一般ごみ)" value="${utils.escapeHtml(item)}">
                <input type="number" class="pr-price" placeholder="単価" style="max-width:80px;" value="${price}">
                <input type="text" class="pr-unit" placeholder="単位(kg等)" style="max-width:70px;" value="${utils.escapeHtml(unit)}">
                <button class="del-btn" onclick="this.parentElement.remove()">×</button>
            `;
            container.appendChild(row);
        }

        function closeModal() { document.getElementById('custOverlay').classList.remove('show'); editingId = null; }

        function openEdit(id) {
            const c = allCustomers.find(x => x.id === id);
            if (c) openModal(c);
        }

        async function saveCustomer() {
            const pricing_list = [];
            document.querySelectorAll('.pricing-row').forEach(row => {
                const item = row.querySelector('.pr-item').value.trim();
                const price = row.querySelector('.pr-price').value.trim();
                const unit = row.querySelector('.pr-unit').value.trim();
                if (item || price) pricing_list.push({ item, price, unit });
            });

            const formData = {
                mobile: document.getElementById('custMobile').value.trim(),
                branch_name: document.getElementById('custBranchName').value.trim(),
                branch_address: document.getElementById('custBranchAddress').value.trim(),
                industry_type: document.getElementById('custIndustryType').value,
                average_volume: document.getElementById('custAvgVolume').value.trim(),
                collection_general: document.getElementById('custFreqGeneral').value.trim(),
                collection_recycle: document.getElementById('custFreqRecycle').value.trim(),
                collection_plastic: document.getElementById('custFreqPlastic').value.trim(),
                collection_paper: document.getElementById('custFreqPaper').value.trim(),
                business_hours: document.getElementById('custBusinessHours').value.trim(),
                regular_holiday: document.getElementById('custHoliday').value.trim(),
                collection_start_date: document.getElementById('custStartDate').value,
                payment_method: document.getElementById('custPaymentMethod').value,
                billing_address: document.getElementById('custBillingAddress').value.trim(),
                billing_email: document.getElementById('custBillingEmail').value.trim(),
                billing_contact: document.getElementById('custBillingContact').value.trim(),
                pricing_list: pricing_list
            };

            const body = {
                name: document.getElementById('custName').value.trim(),
                contact_person: document.getElementById('custContact').value.trim(),
                address: document.getElementById('custAddress').value.trim(),
                phone: document.getElementById('custPhone').value.trim(),
                email: document.getElementById('custEmail').value.trim(),
                contract_type: document.getElementById('custType').value,
                contract_expiry_date: document.getElementById('custExpiry').value || null,
                billing_closing_day: parseInt(document.getElementById('custClosingDay').value) || 31,
                payment_due_month_offset: parseInt(document.getElementById('custPayMonthOffset').value) || 1,
                payment_due_day: parseInt(document.getElementById('custPayDay').value) || 31,
                notes: document.getElementById('custNotes').value.trim(),
                form_data: JSON.stringify(formData)
            };
            if (!body.name) { alert('顧客名を入力してください'); return; }
            try {
                if (editingId) {
                    await RyubeeAPI.updateCustomer(editingId, body);
                    showToast('✅ 更新しました');
                } else {
                    await RyubeeAPI.createCustomer(body);
                    showToast('✅ 登録しました');
                }
                closeModal();
                loadCustomers();
            } catch (e) { alert('エラー: ' + e.message); }
        }

        async function deleteCustomer() {
            if (!editingId || !confirm('この顧客を削除しますか？')) return;
            try {
                await RyubeeAPI.deleteCustomer(editingId);
                closeModal();
                showToast('🗑 削除しました');
                loadCustomers();
            } catch (e) { alert('エラー: ' + e.message); }
        }

        function showToast(msg) {
            const t = document.createElement('div');
            t.textContent = msg;
            t.style.cssText = 'position:fixed;bottom:90px;left:50%;transform:translateX(-50%);background:#34C759;color:#fff;padding:10px 20px;border-radius:20px;font-weight:600;z-index:9999;';
            document.body.appendChild(t);
            setTimeout(() => t.remove(), 2500);
        }
    </script>
