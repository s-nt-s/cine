class Db {
    constructor(onerror = null) {
      this.db = supabase.createClient(
    'https://yboiiqazxgmunztgfzbg.supabase.co',
    'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inlib2lpcWF6eGdtdW56dGdmemJnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTIyNDg1NTEsImV4cCI6MjA2NzgyNDU1MX0.u40Y0Ywk9jVk1JKQEjGhT1mYgvMXYrgB1xQ3BttAOWc'
      );
      this.onerror = onerror;
    }

    get_data(log, obj) {
      if (obj.error) {
        console.error(log, obj);
        if (this.onerror) this.onerror(obj.error);
        throw obj.error;
      }
      if (obj.data == null && "count" in obj) {
        const count = obj.count;
        if (typeof count === "number" && !isNaN(count)) {
          console.log(log + ": count(*) = " + count);
          return count;
        }
      }
      console.log(log + ": " + obj.data.length + " resultados");
      return obj.data;
    }

    from(t) {
      return this.db.from(t);
    }

    async get(table, ...ids) {
      return await this.selectTableWhere(table, "id", ...ids);
    }

    async get_one(table, id) {
      const r = await this.selectTableWhere(table, "id", id);
      if (r.length === 1) return r[0];
      throw `${table}[id=${id}] devuelve ${r.length} resultados`;
    }

    async safe_get_one(table, id) {
      if (id == null) return null;
      return this.get_one(table, id);
    }

    async selectTableWhere(table, where_fieldName, ...arr) {
      return await this.__selectWhere(table, undefined, where_fieldName, ...arr);
    }

    async selectColumnWhere(table, fieldName, where_fieldName, ...arr) {
      const r = await this.__selectWhere(table, fieldName, where_fieldName, ...arr);
      return r.map(i => i[fieldName]);
    }

    async __selectWhere(table, fieldName, where_fieldName, ...arr) {
      const field = fieldName || "*";
      const where_field = where_fieldName || undefined;
      const table_field = table + "." + field;
      const prm = this.__buildSelectWhere(table, fieldName, where_fieldName, ...arr);
      const r = this.get_data(
        arr.length === 0 ? table_field : `${table_field}[${where_field}=${arr}]`,
        await prm
      );
      if (r.length === 0) return r;
      if (field !== "*") {
        const id = "id" in r[0] ? r[0].id : null;
        if (typeof id === "number") return r.sort((a, b) => b.id - a.id);
        if (typeof id === "string") return r.sort((a, b) => b.id.localeCompare(a.id));
      }
      return r;
    }

    __unpackWhereArg(v) {
      if (typeof v !== "string") return null;
      const m = v.match(/^(<|>|<=|>=|!)(\d+)$/);
      if (!m) return null;
      const n = parseInt(m[2]);
      if (isNaN(n)) return null;
      return [m[1], n];
    }

    __buildSelectWhere(table, fieldName, where_fieldName, ...arr) {
      const field = fieldName || "*";
      const where_field = where_fieldName || undefined;
      let prm = this.from(table).select(field);
      if (where_field && arr.length > 0) {
        const _in_ = [];
        arr.forEach(a => {
          const unpack = this.__unpackWhereArg(a);
          if (unpack == null) {
            _in_.push(a);
            return;
          }
          const [op, val] = unpack;
          if (op === ">") prm = prm.gt(where_field, val);
          else if (op === "<") prm = prm.lt(where_field, val);
          else if (op === "<=") prm = prm.lte(where_field, val);
          else if (op === ">=") prm = prm.gte(where_field, val);
          else if (op === "!") prm = prm.neq(where_field, val);
          else throw "Bad argument: " + op;
        });
        if (_in_.length === 1) prm = prm.eq(where_field, _in_[0]);
        else if (_in_.length > 1) prm = prm.in(where_field, _in_);
      }
      return prm;
    }

    async __minmax(ascending, table, field, where_fieldName, ...arr) {
      const table_field = table + "." + field;
      const prm = this.__buildSelectWhere(table, field, where_fieldName, ...arr)
        .order(field.toString(), { ascending: ascending, nullsFirst: false })
        .limit(1);
      const log = arr.length === 0 || !where_fieldName ? table_field : `${table_field}[${where_fieldName}=${arr}]`;
      const logline = `${ascending ? "min" : "max"}(${log})`;
      const tval = this.get_data(logline, await prm);
      const val = tval[0][field];
      console.log(logline + " = " + val);
      return val;
    }

    async min(table, field, where_fieldName, ...arr) {
      return await this.__minmax(true, table, field, where_fieldName, ...arr);
    }

    async max(table, field, where_fieldName, ...arr) {
      return await this.__minmax(false, table, field, where_fieldName, ...arr);
    }
  }